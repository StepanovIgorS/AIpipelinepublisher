import logging
from contextlib import asynccontextmanager
from datetime import datetime
from urllib.parse import urlparse
from uuid import uuid4

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import LabeledPrice
from aiogram.utils.keyboard import InlineKeyboardBuilder
from celery import Celery, chain, signature
from fastapi import FastAPI, HTTPException, Request, status

from api.config import settings
from api.database import Database
from api.lang import FAILED_PARSE_LINK_MSG, INITIAL_PROMPT, PROMPT_SUCCESS, WELCOME_MSG
from api.model import (
    Length,
    Payments,
    Platform,
    Settings,
    TaskStatus,
    UpdateStatusRequest,
    UserSettings,
)
from api.platforms import classify_platform, normalize_url

logging.basicConfig(level=logging.INFO, force=True)

logger = logging.getLogger(__name__)

db = Database()

bot = Bot(token=settings.TG_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
celery = Celery(
    "worker_pipeline", broker=settings.REDIS_URL, backend=settings.REDIS_URL
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(
        settings.WEBHOOK_URL, secret_token=settings.TELEGRAM_SECRET_TOKEN
    )
    logger.log(logging.INFO, f"Webhook set to {settings.WEBHOOK_URL}")
    await db.init_pool()
    yield
    await db.close()
    await bot.delete_webhook(drop_pending_updates=True)
    logger.log(logging.INFO, "Webhook deleted")


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.post("/webhook")
async def webhook(request: Request):
    bot_update = types.Update.model_validate(await request.json(), context={"bot": bot})
    if settings.TELEGRAM_SECRET_TOKEN != request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token"
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    await dp.feed_update(bot, bot_update)
    logger.debug("Update received: %s", bot_update)
    return {"status": "ok"}


@app.post("/internal/status/{uid}")
async def download_status(request: Request, uid: str, body: UpdateStatusRequest):
    if request.headers.get("X-Internal-Token") != settings.INTERNAL_SECRET:
        logger.error("Unauthorized access attempt to /internal/status/%s", uid)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    if body.status == TaskStatus.error:
        await db.execute(
            "UPDATE tasks SET status = $1, error = $2 WHERE uuid = $3",
            body.status,
            body.error,
            uid,
        )
        logger.info("task %s failed with error: %s", uid, body.error)
        return {"status": "ok"}
    await db.execute("UPDATE tasks SET status = $1 WHERE uuid = $2", body.status, uid)
    logger.info("task %s status update success", uid)
    return {"status": "ok"}


@app.post("/internal/complete/{uid}")
async def complete_task(request: Request, uid: str):
    if request.headers.get("X-Internal-Token") != settings.INTERNAL_SECRET:
        logger.error("Unauthorized access attempt to /internal/status/%s", uid)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    await db.execute(
        "UPDATE tasks SET status = $1 WHERE uuid = $2", TaskStatus.completed, uid
    )
    await db.execute(
        "UPDATE users SET free_gens = free_gens - 1 WHERE telegram_id = (SELECT telegram_id FROM tasks WHERE uuid = $1) AND premium IS NULL",
        uid,
    )
    logger.info("task %s completed", uid)
    return {"status": "ok"}


@dp.message(Command("start"), F.chat.type == "private", StateFilter("*"))
async def start(message: types.Message, state: FSMContext):
    if not message.from_user:
        return
    if not await db.fetchone(
        "SELECT * FROM users WHERE telegram_id = $1", message.from_user.id
    ):
        await db.execute(
            "INSERT INTO users (telegram_id) VALUES ($1)", message.from_user.id
        )
        logger.info("New user registered: %s", message.from_user.id)
    await message.answer(WELCOME_MSG)
    await message.answer(INITIAL_PROMPT)
    builder = InlineKeyboardBuilder()
    builder.button(text=Platform.VK, callback_data=Platform.VK)
    builder.button(text=Platform.TELEGRAM, callback_data=Platform.TELEGRAM)
    await message.answer("Выбери платформу", reply_markup=builder.as_markup())
    await state.set_state(Settings.platform)
    logger.info("user %s started the process of registration", message.from_user.id)


@dp.callback_query(Settings.platform)
async def platform_chosen(callback: types.CallbackQuery, state: FSMContext):
    if not callback.message or not isinstance(callback.message, types.Message):
        logger.error(
            "Invalid callback message for platform choice for user %s",
            callback.from_user.id,
        )
        return  # TODO: потом что-нибудь придумаем
    await state.update_data(platform=callback.data)
    await callback.message.answer(
        "Отлично! Теперь напиши, для какой аудитории ты хочешь подготовить текст (например: «для студентов», «для руководителей», «для родителей» и т.д.)"
    )
    await callback.message.edit_reply_markup(None)
    await callback.answer()
    await state.set_state(Settings.audience)
    logger.info("user %s chose platform: %s", callback.from_user.id, callback.data)


@dp.message(Settings.audience)
async def audience_chosen(message: types.Message, state: FSMContext):
    if not message.text:
        logger.error(
            "Invalid message for audience choice for user %s", message.from_user.id
        )
        return  # TODO: потом что-нибудь придумаем
    await state.update_data(audience=message.text)
    builder = InlineKeyboardBuilder()
    builder.button(text=Length.SHORT, callback_data=Length.SHORT)
    builder.button(text=Length.MEDIUM, callback_data=Length.MEDIUM)
    builder.button(text=Length.LONG, callback_data=Length.LONG)
    await message.answer(
        "Отлично! Теперь выбери длину текста (короткий, средний, длинный)",
        reply_markup=builder.as_markup(),
    )
    await state.set_state(Settings.length)
    logger.info("user %s chose audience: %s", message.from_user.id, message.text)


@dp.callback_query(Settings.length)
async def length_chosen(callback: types.CallbackQuery, state: FSMContext):
    if not callback.message or not isinstance(callback.message, types.Message):
        logger.error(
            "Invalid callback message for length choice for user %s",
            callback.from_user.id,
        )
        return  # TODO: потом что-нибудь придумаем
    await state.update_data(length=callback.data)
    await callback.message.answer("Отлично! Теперь напиши промпт для генерации текста")
    await callback.message.edit_reply_markup(None)
    await callback.answer()
    await state.set_state(Settings.prompt)
    logger.info("user %s chose length: %s", callback.from_user.id, callback.data)


@dp.message(Settings.prompt)
async def prompt_chosen(message: types.Message, state: FSMContext):
    if not message.text or not message.from_user:
        logger.error(
            "Invalid message for prompt choice for user %s", message.from_user.id
        )
        return  # TODO: потом что-нибудь придумаем
    await state.update_data(prompt=message.text)
    user_settings = UserSettings(**await state.get_data())
    await db.execute(
        "UPDATE users SET prompt = $1, platform = $2, audience = $3, length = $4 WHERE telegram_id = $5",
        user_settings.prompt,
        user_settings.platform,
        user_settings.audience,
        user_settings.length,
        message.from_user.id,
    )
    await message.answer(PROMPT_SUCCESS)
    await state.clear()
    logger.info("user %s completed settings: %s", message.from_user.id, user_settings)


@dp.message(Command("premium"), F.chat.type == "private", StateFilter("*"))
async def premium(message: types.Message, state: FSMContext):
    if not message.from_user:
        return
    if not await db.fetchone(
        "SELECT * FROM users WHERE telegram_id = $1", message.from_user.id
    ):
        await message.answer("Пожалуйста, зарегистрируйся, используя команду /start.")
        return
    logger.info("user %s requested premium subscription", message.from_user.id)
    builder = InlineKeyboardBuilder()
    builder.button(text="1 месяц", callback_data="1_month")
    builder.button(text="3 месяца", callback_data="3_months")
    builder.button(text="6 месяцев", callback_data="6_months")
    builder.button(text="отмена", callback_data="cancel")
    await message.answer("Выбери подписку", reply_markup=builder.as_markup())
    await state.set_state(Payments.choosing_subscription)


@dp.callback_query(Payments.choosing_subscription)
async def subscription_chosen(callback: types.CallbackQuery, state: FSMContext):
    if not callback.message or not isinstance(callback.message, types.Message):
        logger.error(
            "Invalid callback message for subscription choice for user %s",
            callback.from_user.id,
        )
        return  # TODO: потом что-нибудь придумаем
    if callback.data == "cancel":
        await callback.message.delete()
        await callback.answer("Действие отменено")
        await state.clear()
        return
    await callback.message.delete()
    month, price = settings.PRICING.get(callback.data, (None, None))
    if not month or not price:
        logger.warning(
            "Invalid subscription choice %s for user %s",
            callback.data,
            callback.from_user.id,
        )
        await callback.answer("Ошибка. Повторите попытку", show_alert=True)
        await state.clear()
        return
    uid = uuid4()
    invoice = await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"Подписка на {month} месяцев",
        description="Подписка на сервис",
        payload=str(uid),
        currency="RUB",
        provider_token=settings.PAYMENT_TOKEN,
        prices=[LabeledPrice(label="Подписка", amount=price)],
    )
    await db.execute(
        "INSERT INTO payments(uuid, user_id, plan, invoice_message_id) VALUES ($1, $2, $3, $4)",
        uid,
        callback.from_user.id,
        int(month),
        invoice.message_id,
    )
    logger.info(
        "user %s initiated payment for %s months subscription, invoice id: %s",
        callback.from_user.id,
        month,
        uid,
    )
    await callback.answer()
    await state.set_state(Payments.pending)


@dp.pre_checkout_query()
async def pre_checkout(query: types.PreCheckoutQuery):
    try:
        bill = await db.fetchone(
            "SELECT user_id, status FROM payments WHERE uuid = $1",
            query.invoice_payload,
        )
    except Exception:
        logger.exception(
            "Error occurred while fetching payment for user %s", query.from_user.id
        )
        await query.answer(
            ok=False,
            error_message="Произошла ошибка при обработке оплаты! Попробуйте создать счёт повторно",
        )
        return
    if not bill or bill["status"] != "pending" or bill["user_id"] != query.from_user.id:
        await query.answer(ok=False, error_message="Счёт уже оплачен!")
        logger.warning(
            "Pre-checkout query failed for user %s: bill not found or already paid",
            query.from_user.id,
        )
        return
    await query.answer(ok=True)


@dp.message(F.successful_payment)
async def successful_payment(message: types.Message, state: FSMContext):
    bill = await db.fetchone(
        "SELECT status, plan, invoice_message_id FROM payments WHERE uuid = $1",
        message.successful_payment.invoice_payload,
    )
    if not bill or bill["status"] != "pending":
        return
    await db.execute(
        "WITH updated_payment AS (UPDATE payments SET status='paid', paid_at = NOW() WHERE uuid = $1 AND status = 'pending' RETURNING 1) UPDATE users SET premium = COALESCE(premium, now()) + ($2 * INTERVAL '1 month') WHERE telegram_id = $3 AND EXISTS(SELECT 1 FROM updated_payment)",
        message.successful_payment.invoice_payload,
        bill["plan"],
        message.from_user.id,
    )
    await bot.delete_message(
        chat_id=message.from_user.id, message_id=bill["invoice_message_id"]
    )
    await state.clear()
    await message.answer(
        "Поздравляем с оплатой подписки! пользуйтесь всеми возможностями премиум!"
    )
    logger.info(
        "user %s successfully paid for subscription, plan: %s",
        message.from_user.id,
        bill["plan"],
    )


@dp.message(F.chat.type == "private", StateFilter(None))
async def on_message(message: types.Message):
    if message.from_user is None or not message.text:
        return None
    if not await db.fetchone(
        "SELECT * FROM users WHERE telegram_id = $1", message.from_user.id
    ):
        logger.warning(
            "User %s not found in database. Prompting to register.",
            message.from_user.id,
        )
        return await message.answer(
            "Пожалуйста, зарегистрируйся, используя команду /start."
        )
    try:
        normalized = normalize_url(message.text)
        url = urlparse(normalized)
        platform = classify_platform(normalized)
        if platform == "unknown":
            return await message.answer(FAILED_PARSE_LINK_MSG)
        logger.info(
            "Classified platform for user %s: %s", message.from_user.id, platform
        )
    except ValueError:
        logger.error(
            "Error occurred while parsing URL for user %s: %s",
            message.from_user.id,
            message.text,
        )
        return await message.answer(FAILED_PARSE_LINK_MSG)
    active_task = await db.fetchone(
        "SELECT * FROM tasks WHERE telegram_id = $1 AND status=ANY($2)",
        message.from_user.id,
        [
            TaskStatus.pending,
            TaskStatus.downloading,
            TaskStatus.transcribing,
            TaskStatus.summarizing,
        ],
    )
    if active_task:
        logger.warning(
            "User %s already has an active task %s in the queue.",
            message.from_user.id,
            active_task["uuid"],
        )
        # return await message.answer("У тебя уже есть задача в очереди.") TODO: временно!
    user = await db.fetchone(
        "SELECT * FROM users WHERE telegram_id = $1", message.from_user.id
    )
    premium_until = user["premium"]
    if isinstance(premium_until, datetime) and premium_until < datetime.now():
        await db.execute(
            "UPDATE users SET premium = NULL WHERE telegram_id = $1",
            message.from_user.id,
        )
        premium_until = None
        logger.info("User %s premium expired. Updated database.", message.from_user.id)
    if (
        isinstance(user["free_gens"], int)
        and user["free_gens"] <= 0
        and not premium_until
    ):
        logger.warning(
            "User %s has exhausted free generations and is not premium. Aborting",
            message.from_user.id,
        )
        return await message.answer(
            "Использован лимит бесплатных генераций. Пожалуйста, обнови тариф или подожди до следующего месяца."
        )
    queue = await db.fetchone(
        "SELECT count(*) cnt FROM tasks WHERE status = $1", TaskStatus.pending
    )
    await db.execute(
        "INSERT INTO tasks(telegram_id, uuid, status) VALUES ($1, $2, $3)",
        message.from_user.id,
        uuid := str(uuid4()),
        TaskStatus.pending,
    )
    user_settings = UserSettings(
        user["platform"], user["audience"], user["length"], user["prompt"]
    )
    if url.hostname in settings.VIDEO_LINKS:
        chain(
            signature(
                "video.download",
                args=[
                    message.from_user.id,
                    uuid,
                    message.text,
                    platform,
                    bool(premium_until),
                ],
            ),
            signature("ai.transcribe"),
            signature("ai.summary", args=[user_settings.build_summary_prompt()]),
        ).delay()
        logger.info(
            "Task for user %s added to queue: %s (video), queue count %s",
            message.from_user.id,
            uuid,
            queue["cnt"],
        )
    elif url.hostname in settings.ARTICLE_LINKS:
        chain(
            signature(
                "article.fetch",
                args=[message.from_user.id, uuid, message.text, platform],
            ),
            signature("ai.summary", args=[user_settings.build_summary_prompt()]),
        ).delay()
        logger.info(
            "Task for user %s added to queue: %s (article), queue count %s",
            message.from_user.id,
            uuid,
            queue["cnt"],
        )
    return await message.answer(
        f"Задача поставлена в очередь на обработку. Ты получишь уведомление, когда она будет завершена.\n\nПозиция в очереди: {queue['cnt']}"
    )
