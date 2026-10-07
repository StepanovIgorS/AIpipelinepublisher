import asyncio
import os

from aiogram import Bot

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
bot = Bot(token=os.getenv("BOT_TOKEN"))
MAX_MESSAGE_LENGTH = 4096


def split_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    return [text[i : i + max_length] for i in range(0, len(text), max_length)]


class TelegramNotifier:
    @staticmethod
    def send_message(user_id: int, text: str):
        for chunk in split_message(text):
            loop.run_until_complete(bot.send_message(chat_id=user_id, text=chunk))

    @staticmethod
    def shutdown():
        if bot.session is not None:
            loop.run_until_complete(bot.session.close())
            loop.close()
