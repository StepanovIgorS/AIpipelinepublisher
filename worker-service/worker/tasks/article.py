from dataclasses import asdict

from celery import shared_task
import requests
from bs4 import BeautifulSoup
from worker.enums import TaskStatus
from worker.utils import update_status
from worker.models import ArticleContext
import re
import json
import os


INTERNAL_SECRET = os.getenv("INTERNAL_SECRET") or ""


def habr_parser(url: str) -> tuple[str, str]:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")
    title = soup.find("h1", class_="tm-title")
    raw_content = soup.find("div", class_="article-formatted-body").find("div")
    content = "\n\n".join(x.get_text() for x in raw_content.find_all(True) if x.name in ("p", "h3"))
    return title.get_text() if title else "No title", content

def pikabu_parser(url: str) -> tuple[str, str]:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")
    title = soup.find("span", class_="story__title-link")
    raw_content = soup.find("div", class_="story__content-inner").find_all("div")
    content = "\n\n".join(x.get_text() for x in raw_content)
    return title.get_text() if title else "No title", content


def fetch_dzen_article(url: str) -> bytes:
    session = requests.Session()
    response = session.get(url, timeout=30)
    response.raise_for_status()

    text = response.text
    match = re.search(r"var it = (\{.*?\});", text)
    if not match:
        raise ValueError("Dzen SSO config not found")

    it = json.loads(match.group(1))
    container_match = re.search(
        r"element2\.value = '([^']*)';",
        text
    )
    if not container_match:
        raise ValueError("Dzen SSO container not found")

    container = container_match.group(1)
    session.post(
        it["host"],
        data={
            "retpath": it["retpath"],
            "container": container,
            "dzen": "1",
        },
        timeout=30,
    )
    article_response = session.get(
        it["retpath"],
        timeout=30,
    )
    article_response.raise_for_status()
    return article_response.content

def dzen_parser(url: str) -> tuple[str, str]:
    article_response = fetch_dzen_article(url)
    soup = BeautifulSoup(article_response, "html.parser")
    script = next(
        script
        for script in soup.find_all("script")
        if "set-ssr-data-to-req-context.ts" in script.get_text()
    )

    script_text = script.get_text()

    start = script_text.index("var _params=(") + len("var _params=(")

    payload, _ = json.JSONDecoder().raw_decode(
        script_text[start:]
    )

    publication = (
        payload["ssrData"]
        ["publishersResponse"]
        ["data"]
        ["data"]
        ["publication"]
    )

    title = payload["ssrData"]["publishersResponse"]["data"]["title"]

    content_state = json.loads(
        publication["content"]
        ["articleContent"]
        ["contentState"]
    )

    blocks = content_state["draftJsState"]["blocks"]
    content = "\n\n".join(block.get("text") for block in blocks if block.get("text"))
    return title, content

ARTICLE_PARSERS = {
    "habr": habr_parser,
    "pikabu": pikabu_parser,
    "dzen": dzen_parser
}

@shared_task(name="article.fetch")
def article_fetch(user_id: int, uuid: str, url: str, platform: str):
    update_status(uuid, TaskStatus.downloading)
    parser = ARTICLE_PARSERS.get(platform)
    parser(url)
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