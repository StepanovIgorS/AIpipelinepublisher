import os
import logging

import requests

from worker.enums import TaskStatus
from worker.models import ArticleContext, Context, VideoContext
from worker.notifier import TelegramNotifier

INTERNAL_SECRET = os.getenv("INTERNAL_SECRET") or ""
error_text = "😔 Упс! Не удалось распознать эту ссылку.\n\nПроверь, что ссылка:\n\n* 🔗 ведет на YouTube или статью в интернете;\n* 🌐 доступна без ограничений;\n* 📋 скопирована полностью, без лишних символов.\n\nПопробуй отправить ссылку еще раз — и я сразу подготовлю красивую выжимку, оформлю пост в нужном стиле и отправлю его в канал. 🚀"
logger = logging.getLogger(__name__)

def get_context_from_dict(ctx: dict) -> Context:
    if ctx.get("context_type") == "video":
        return VideoContext(**ctx)
    if ctx.get("context_type") == "article":
        return ArticleContext(**ctx)
    raise ValueError("Invalid context type")


def update_status(uuid: str, status: TaskStatus, error: str | None = None):
    if error:
        requests.post(
            f"http://api-service:8000/internal/status/{uuid}",
            headers={"X-Internal-Token": INTERNAL_SECRET},
            json={"status": TaskStatus.error, "error": error},
            timeout=5,
        )
    else:
        requests.post(
            f"http://api-service:8000/internal/status/{uuid}",
            headers={"X-Internal-Token": INTERNAL_SECRET},
            json={"status": status},
            timeout=5,
        )
    logger.info("task %s status update api call was sent, new status is %s", uuid, status)


def fail_task(chat, uuid, reason, text=None):
    requests.post(
        f"http://api-service:8000/internal/status/{uuid}",
        headers={"X-Internal-Token": INTERNAL_SECRET},
        json={"status": TaskStatus.error, "error": reason},
    )
    TelegramNotifier.send_message(user_id=chat, text=text if text else error_text)
    logger.info("task %s fail api call was sent with reason: %s", uuid, reason)


def complete(ctx: Context):
    if isinstance(ctx, VideoContext):
        if ctx.transcription_path:
            os.remove(ctx.transcription_path)
        if ctx.audio_path:
            os.remove(ctx.audio_path)
    requests.post(
        f"http://api-service:8000/internal/complete/{ctx.uuid}",
        headers={"X-Internal-Token": INTERNAL_SECRET},
        timeout=5,
    )
    logger.info("task %s complete api call was sent", ctx.uuid)


def cleanup(ctx: Context):
    logger.info("Task %s force cleaning up tmp files", ctx.uuid)
    if isinstance(ctx, VideoContext):
        if ctx.transcription_path:
            os.remove(ctx.transcription_path)
        if ctx.audio_path:
            os.remove(ctx.audio_path)