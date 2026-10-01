import os
from dotenv import load_dotenv
load_dotenv()

class Settings:
    POSTGRES_URL: str = os.getenv('POSTGRES_URL')
    REDIS_URL: str = os.getenv('REDIS_URL')
    TG_TOKEN: str = os.getenv('BOT_TOKEN')
    AI_KEY: str = os.getenv('OPENAI_API_KEY')
    WEBHOOK_URL: str = os.getenv('WEBHOOK_URL')
    TELEGRAM_SECRET_TOKEN: str = os.getenv('TELEGRAM_SECRET_TOKEN')
    INTERNAL_SECRET: str = os.getenv('INTERNAL_SECRET')
    VIDEO_LINKS: list[str] = ["youtu.be", "youtube.com", "rutube.ru", "vkvideo.ru", "www.youtu.be", "www.youtube.com", "www.rutube.ru", "www.vkvideo.ru"]
    ARTICLE_LINKS: list[str] = ["habr.com", "www.habr.com", "pikabu.ru", "www.pikabu.ru", "dzen.ru", "www.dzen.ru"]

settings = Settings()