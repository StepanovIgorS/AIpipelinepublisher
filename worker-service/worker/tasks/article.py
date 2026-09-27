from dataclasses import asdict

from celery import shared_task
import requests
from bs4 import BeautifulSoup
from worker.enums import TaskStatus
from worker.utils import update_status
from worker.models import ArticleContext
import os


INTERNAL_SECRET = os.getenv("INTERNAL_SECRET") or ""


def habr_parser(url: str) -> tuple[str, str]:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")
    title = soup.find("h1", class_="tm-title")
    raw_content = soup.find("div", class_="article-formatted-body").find("div")
    content = ""
    for i in raw_content.find_all(True):
        if i.name == "p" or i.name == "h3":
            content += i.get_text() + "\n\n"
    return title.get_text() if title else "No title", content

ARTICLE_PARSERS = {
    "habr": habr_parser
}

@shared_task(name="article.fetch")
def article_fetch(user_id: int, uuid: str, url: str, platform: str):
    update_status(uuid, TaskStatus.downloading)
    parser = ARTICLE_PARSERS.get(platform)
    title, content = parser(url)
    article_path = f"/tmp/{uuid}.txt"
    with open(article_path, "w") as f:
        f.write(content)
    ctx = ArticleContext(
        context_type="article",
        uuid=uuid,
        user_id=user_id,
        title=title,
        description=None,
        platform=platform,
        platform_id=url,
        article_path=article_path
    )
    return asdict(ctx)