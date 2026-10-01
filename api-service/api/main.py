from aiogram.utils.keyboard import InlineKeyboardBuilder
from fastapi import FastAPI, Request, HTTPException, status
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command, StateFilter
from api.config import settings
from api.database import Database
from contextlib import asynccontextmanager
from urllib.parse import urlparse
from api.lang import WELCOME_MSG, FAILED_PARSE_LINK_MSG, INITIAL_PROMPT, PROMPT_SUCCESS
import logging
from celery import Celery, chain, signature
from uuid import uuid4
from api.model import UpdateStatusRequest, TaskStatus, Settings, Platform, Length, UserSettings


logging.basicConfig(level=logging.INFO, force=True)

db = Database()
celery = Celery(
    'worker_pipeline',
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)
@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(settings.WEBHOOK_URL, secret_token=settings.TELEGRAM_SECRET_TOKEN)
    logging.log(logging.INFO, f"Webhook set to {settings.WEBHOOK_URL}")
    await db.init_pool()
    yield
    await db.close()
    await bot.delete_webhook(drop_pending_updates=True)
    logging.log(logging.INFO, f"Webhook deleted")

app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
bot = Bot(token=settings.TG_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

@app.post("/webhook")
async def webhook(request: Request):
    bot_update = types.Update.model_validate(await request.json(), context={"bot": bot})
    if settings.TELEGRAM_SECRET_TOKEN != request.headers.get("X-Telegram-Bot-Api-Secret-Token"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    await dp.feed_update(bot, bot_update)
    return {"status": "ok"}

@app.post("/internal/status/{uid}")
async def download_status(request: Request, uid: str, body: UpdateStatusRequest):
    if request.headers.get("X-Internal-Token") != settings.INTERNAL_SECRET:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    if body.status == TaskStatus.error:
        await db.execute("UPDATE tasks SET status = $1, error = $2 WHERE uuid = $3", body.status, body.error, uid)
        return {"status": "ok"}
    await db.execute("UPDATE tasks SET status = $1 WHERE uuid = $2", body.status, uid)
    return {"status": "ok"}

@app.post("/internal/complete/{uid}")
async def complete_task(request: Request, uid: str):
    if request.headers.get("X-Internal-Token") != settings.INTERNAL_SECRET:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    await db.execute("UPDATE tasks SET status = $1 WHERE uuid = $2", TaskStatus.completed, uid)
    await db.execute("UPDATE users SET free_gens = free_gens - 1 WHERE telegram_id = (SELECT telegram_id FROM tasks WHERE uuid = $1)", uid)
    return {"status": "ok"}

@dp.message(Command('start'), F.chat.type == "private", StateFilter("*"))
async def start(message: types.Message, state: FSMContext):
    if not message.from_user:
        return
    if not await db.fetchone("SELECT * FROM users WHERE telegram_id = $1", message.from_user.id):
        await db.execute("INSERT INTO users (telegram_id) VALUES ($1)", message.from_user.id)
    await message.answer(WELCOME_MSG)
    await message.answer(INITIAL_PROMPT)
    builder = InlineKeyboardBuilder()
    builder.button(
        text=Platform.VK,
        callback_data=Platform.VK
    )
    builder.button(
        text=Platform.TELEGRAM,
        callback_data=Platform.TELEGRAM
    )
    await message.answer("Выбери платформу", reply_markup=builder.as_markup())
    await state.set_state(Settings.platform)


@dp.callback_query(Settings.platform)
async def platform_chosen(callback: types.CallbackQuery, state: FSMContext):
    if not callback.message or not isinstance(callback.message, types.Message):
        return # TODO: потом что-нибудь придумаем
    await state.update_data(platform=callback.data)
    await callback.message.answer("Отлично! Теперь напиши, для какой аудитории ты хочешь подготовить текст (например: «для студентов», «для руководителей», «для родителей» и т.д.)")
    await callback.message.edit_reply_markup(None)
    await callback.answer()
    await state.set_state(Settings.audience)

@dp.message(Settings.audience)
async def audience_chosen(message: types.Message, state: FSMContext):
    if not message.text:
        return # TODO: потом что-нибудь придумаем
    await state.update_data(audience=message.text)
    builder = InlineKeyboardBuilder()
    builder.button(
        text=Length.SHORT,
        callback_data=Length.SHORT
    )
    builder.button(
        text=Length.MEDIUM,
        callback_data=Length.MEDIUM
    )
    builder.button(
        text=Length.LONG,
        callback_data=Length.LONG
    )
    await message.answer("Отлично! Теперь выбери длину текста (короткий, средний, длинный)", reply_markup=builder.as_markup())
    await state.set_state(Settings.length)

@dp.callback_query(Settings.length)
async def length_chosen(callback: types.CallbackQuery, state: FSMContext):
    if not callback.message or not isinstance(callback.message, types.Message):
        return # TODO: потом что-нибудь придумаем
    await state.update_data(length=callback.data)
    await callback.message.answer("Отлично! Теперь напиши промпт для генерации текста")
    await callback.message.edit_reply_markup(None)
    await callback.answer()
    await state.set_state(Settings.prompt)

@dp.message(Settings.prompt)
async def prompt_chosen(message: types.Message, state: FSMContext):
    if not message.text or not message.from_user:
        return # TODO: потом что-нибудь придумаем
    await state.update_data(prompt=message.text)
    user_settings = UserSettings(**await state.get_data())
    await db.execute("UPDATE users SET prompt = $1, platform = $2, audience = $3, length = $4 WHERE telegram_id = $5", user_settings.prompt, user_settings.platform, user_settings.audience, user_settings.length, message.from_user.id)
    await message.answer(PROMPT_SUCCESS)
    await state.clear()

def classify_platform(url: str) -> str:
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        return "unknown"

    hostname = hostname.lower()
    domain_to_platform = {
        "youtube.com": "youtube",
        "youtu.be": "youtube",
        "rutube.ru": "rutube",
        "vkbideo.ru": "vkbideo",
        "habr.com": "habr",
        "pikabu.ru": "pikabu",
        "dzen.ru": "dzen"
    }

    if hostname not in settings.VIDEO_LINKS + settings.ARTICLE_LINKS:
        return "unknown"

    for domain, platform in domain_to_platform.items():
        if hostname == domain or hostname.endswith(f".{domain}"):
            if platform == "dzen" and parsed.path.strip("/").split("/")[0] != "a":
                return "unknown"
            return platform

    return hostname

@dp.message(F.chat.type == "private", StateFilter(None)) # todo: проверка регистрации пользователя
async def on_message(message: types.Message):
    if message.from_user is None or not message.text:
        return None
    try:
        url = urlparse(message.text)
        platform = classify_platform(message.text)
        if platform == "unknown":
            return await message.answer(FAILED_PARSE_LINK_MSG)
    except ValueError:
        return await message.answer(FAILED_PARSE_LINK_MSG)
    active_task = await db.fetchone("SELECT * FROM tasks WHERE telegram_id = $1 AND status=ANY($2)", message.from_user.id, [TaskStatus.pending, TaskStatus.downloading, TaskStatus.transcribing, TaskStatus.summarizing])
    if active_task:
        pass
        # return await message.answer("У тебя уже есть задача в очереди.") TODO: временно!
    free_gens = await db.fetchval("SELECT free_gens FROM users WHERE telegram_id = $1", message.from_user.id)
    if isinstance(free_gens, int) and free_gens <= 0:
        return await message.answer("Использован лимит бесплатных генераций. Пожалуйста, обнови тариф или подожди до следующего месяца.")
    queue = await db.fetchone("SELECT count(*) cnt FROM tasks WHERE status = $1", TaskStatus.pending)
    await db.execute("INSERT INTO tasks(telegram_id, uuid, status) VALUES ($1, $2, $3)", message.from_user.id, uuid := str(uuid4()), TaskStatus.pending)
    user =  await db.fetchone("SELECT * FROM users WHERE telegram_id = $1", message.from_user.id)
    user_settings = UserSettings(user["platform"], user["audience"], user['length'], user['prompt'])
    if url.hostname in settings.VIDEO_LINKS:
        chain(
            signature("video.download", args=[message.from_user.id, uuid, message.text, platform]),
            signature("ai.transcribe"),
            signature("ai.summary", args=[user_settings.build_summary_prompt()]),
        ).delay()
    if url.hostname in settings.ARTICLE_LINKS:
        chain(
            signature("article.fetch", args=[message.from_user.id, uuid, message.text, platform]),
            signature("ai.summary", args=[user_settings.build_summary_prompt()]),
        ).delay()
    return await message.answer(f"Задача поставлена в очередь на обработку. Ты получишь уведомление, когда она будет завершена.\n\nПозиция в очереди: {queue['cnt']}")