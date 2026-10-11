import math
import os
import logging

from collections.abc import Iterator
from dataclasses import asdict
from io import BytesIO
from typing import BinaryIO

from celery import shared_task
from openai import APITimeoutError, OpenAI
from openai.types.chat import (
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from worker.cache import Cache
from worker.enums import TaskStatus
from worker.models import ArticleContext, Context, VideoContext
from worker.notifier import TelegramNotifier
from worker.utils import (
    cleanup,
    complete,
    fail_task,
    get_context_from_dict,
    update_status,
)

INTERNAL_SECRET = os.getenv("INTERNAL_SECRET") or ""
STT_MODEL = os.getenv("AI_STT_MODEL") or ""
TEXT_MODEL = os.getenv("AI_TEXT_MODEL") or ""
SYSTEM_PROMPT = """
Ты — профессиональный редактор и автор текстов.

Твоя задача — создавать качественные, естественные и полезные тексты на основе предоставленного материала.

Правила работы:

- Используй только информацию из предоставленного контента. Не выдумывай факты, даты, цитаты или события.
- Если информации недостаточно — не додумывай её.
- Выделяй действительно важные мысли, а не пересказывай каждую фразу.
- Пиши простым, живым и естественным русским языком.
- Текст должен выглядеть так, будто его написал человек, а не искусственный интеллект.
- Избегай шаблонных конструкций вроде «Введение», «Итог», «Основные выводы», «В заключение», если пользователь явно этого не просил.
- Не используй нумерованные списки без необходимости.
- Не повторяй одну и ту же мысль разными словами.
- Не используй канцеляризмы и чрезмерно официальный стиль.
- Сохраняй смысл, настроение и контекст исходного материала.
- Если пользователь просит адаптировать текст под определённую аудиторию или площадку — учитывай это.
- Если пользователь просит изменить стиль, формат или объём текста — выполняй это, не нарушая предыдущие правила.

Не обращайся к пользователю.

Не используй фразы:

- Вот вариант текста.
- Предлагаю такой вариант.
- Ниже текст.
- Вот пост.
- Конечно.
- С удовольствием.

Твоя цель — сделать текст интересным, понятным и удобным для чтения."""
MAX_AUDIO_SIZE = 24 * 1024 * 1024
logger = logging.getLogger(__name__)

client = OpenAI(
    base_url=os.getenv("AI_URL"),
    api_key=os.getenv("AI_KEY"),
)


def build_summary_prompt(
    prompt: str, ctx: Context, transcription: str
) -> list[ChatCompletionSystemMessageParam | ChatCompletionUserMessageParam]:
    return [
        ChatCompletionSystemMessageParam(role="system", content=SYSTEM_PROMPT),
        ChatCompletionUserMessageParam(
            role="user",
            content=f"""
<user_request>
{prompt}
</user_request>

<title>
{ctx.title}
</title>

<Description>
{ctx.description or "no description"}
</Description>

<Transcript>
{transcription}
</Transcript>""",
        ),
    ]


def prepare_audio(file: BinaryIO) -> Iterator[BinaryIO]:
    size = os.fstat(file.fileno()).st_size
    if size <= MAX_AUDIO_SIZE:
        yield file
        return
    count = math.ceil(size / MAX_AUDIO_SIZE)
    for i in range(count):
        yield BytesIO(file.read(MAX_AUDIO_SIZE))


@shared_task(name="ai.transcribe")
def ai_transcribe(ctx: dict):
    ctx = VideoContext(**ctx)
    update_status(ctx.uuid, TaskStatus.transcribing)
    if ctx.has_transcription:
        logger.info("task %s skipping transcribe due to cache for user %s", ctx.uuid, ctx.user_id)
        return asdict(ctx)
    transcription_path = f"/tmp/{ctx.uuid}.txt"
    with open(ctx.audio_path, "rb") as audio_file:
        full_transcription = ""
        for n, audio in enumerate(prepare_audio(audio_file)):
            logger.debug("task %s transcribing audio chunk %d for user %s", ctx.uuid, n + 1, ctx.user_id)
            try:
                transcription = client.audio.transcriptions.create(
                    file=audio, model=STT_MODEL, timeout=30
                )
            except APITimeoutError:
                update_status(ctx.uuid, TaskStatus.error)
                logger.error("task %s transcription API timeout for chunk %d for user %s", ctx.uuid, n + 1, ctx.user_id)
                fail_task(
                    ctx.user_id,
                    ctx.uuid,
                    "Transcription timeout",
                    "😔 Упс! Не удалось распознать аудио. Попробуй отправить ссылку еще раз — и я сразу подготовлю красивую выжимку, оформлю пост в нужном стиле и отправлю его в канал. 🚀",
                )
                raise
            full_transcription += "\n" + transcription.text
        with open(transcription_path, "w") as f:
            f.write(full_transcription)
        ctx.transcription_path = transcription_path
        Cache.save_transcription(ctx, full_transcription)
        logger.info("task %s transcription completed and saved to cache for user %s", ctx.uuid, ctx.user_id)
        return asdict(ctx)


@shared_task(name="ai.summary")
def ai_summary(ctx: dict, prompt: str):
    ctx = get_context_from_dict(ctx)
    update_status(ctx.uuid, TaskStatus.summarizing)
    if isinstance(ctx, VideoContext):
        logger.info("task %s reading transcription for user %s", ctx.uuid, ctx.user_id)
        with open(ctx.transcription_path or "", "r") as transcription_file:
            transcription = transcription_file.read()
    if isinstance(ctx, ArticleContext):
        logger.info("task %s reading article for user %s", ctx.uuid, ctx.user_id)
        with open(ctx.article_path or "", "r") as transcription_file:
            transcription = transcription_file.read()
    try:
        summary = client.chat.completions.create(
            model=TEXT_MODEL, messages=build_summary_prompt(prompt, ctx, transcription)
        )
    except APITimeoutError:
        logger.error("task %s summary API timeout for user %s", ctx.uuid, ctx.user_id)
        update_status(ctx.uuid, TaskStatus.error)
        fail_task(
            ctx.user_id,
            ctx.uuid,
            "Summary timeout",
            "😔 Упс! Не удалось обработать текст. Попробуй отправить ссылку еще раз — и я сразу подготовлю красивую выжимку, оформлю пост в нужном стиле и отправлю его в канал. 🚀",
        )
        cleanup(ctx)
        raise
    text = summary.choices[0].message.content or ""
    TelegramNotifier.send_message(ctx.user_id, text)
    complete(ctx)
