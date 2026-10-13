import asyncio
import logging
import os

from aiogram import Bot

MAX_MESSAGE_LENGTH = 4096
logger = logging.getLogger(__name__)


def split_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    return [text[i : i + max_length] for i in range(0, len(text), max_length)]


class TelegramNotifier:
    is_active = False

    @classmethod
    def __start(cls):
        cls.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(cls.loop)
        cls.bot = Bot(token=os.getenv("BOT_TOKEN"))
        cls.is_active = True

    @classmethod
    def send_message(cls, user_id: int, text: str):
        if not cls.is_active:
            cls.__start()
        for n, chunk in enumerate(split_message(text)):
            logger.info("Sending message chunk %d to user %d", n, user_id)
            cls.loop.run_until_complete(
                cls.bot.send_message(chat_id=user_id, text=chunk)
            )

    @classmethod
    def shutdown(cls):
        if cls.bot and cls.bot.session is not None:
            cls.loop.run_until_complete(cls.bot.session.close())
            cls.loop.close()
            cls.is_active = False
