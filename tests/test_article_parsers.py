import json
from unittest.mock import MagicMock, patch

from worker.enums import TaskStatus
from worker.tasks import article
from worker.models import ArticleContext

HABR_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Тестовая статья</title>
</head>
<body>
    <h1 class="tm-title">Тестовая статья Habr</h1>

    <div class="article-formatted-body">
        <div>
            <p>Первый абзац статьи.</p>
            <p>Второй абзац статьи.</p>

            <h3>Важный раздел</h3>

            <p>Третий абзац статьи.</p>
            <span>Этот текст должен игнорироваться.</span>
        </div>
    </div>
</body>
</html>
"""

PIKABU_HTML = """
<!DOCTYPE html>
<html>
<body>
    <span class="story__title-link">
        Тестовая история Pikabu
    </span>

    <div class="story__content-inner">
        <div>Первый абзац истории.</div>
        <div>Второй абзац истории.</div>
        <div>Третий абзац истории.</div>
    </div>
</body>
</html>
"""


def make_dzen_html() -> str:
    content_state = {
        "draftJsState": {
            "blocks": [
                {"text": "Первый абзац статьи Дзена."},
                {"text": ""},
                {"text": "Второй абзац статьи Дзена."},
                {"text": "Заключительная мысль."},
            ]
        }
    }

    payload = {
        "ssrData": {
            "publishersResponse": {
                "data": {
                    "title": "Тестовая статья Дзена",
                    "data": {
                        "publication": {
                            "content": {
                                "articleContent": {
                                    "contentState": json.dumps(
                                        content_state,
                                        ensure_ascii=False,
                                    )
                                }
                            }
                        }
                    },
                }
            }
        }
    }

    serialized_payload = json.dumps(
        payload,
        ensure_ascii=False,
    )

    return f"""
    <!DOCTYPE html>
    <html>
    <body>
        <script>
            /* set-ssr-data-to-req-context.ts */
            var _params=({serialized_payload});
        </script>
    </body>
    </html>
    """


def test_habr_parser():
    with patch("worker.tasks.article.requests.get") as mock_get:
        mock_get.return_value.content = HABR_HTML
        title, content = article.habr_parser("https://example.com")

        assert title == "Тестовая статья Habr"
        assert content == "Первый абзац статьи.\n\nВторой абзац статьи.\n\nВажный раздел\n\nТретий абзац статьи."
        mock_get.assert_called_once_with("https://example.com", timeout=30)

def test_pikabu_parser():
    with patch("worker.tasks.article.requests.get") as mock_get:
        mock_get.return_value.content = PIKABU_HTML
        title, content = article.pikabu_parser("https://example.com")

        assert title.strip() == "Тестовая история Pikabu"
        assert content == "Первый абзац истории.\n\nВторой абзац истории.\n\nТретий абзац истории."
        mock_get.assert_called_once_with("https://example.com", timeout=30)

def test_dzen_parser():
    with patch("worker.tasks.article.fetch_dzen_article") as mock_fetch:
        mock_fetch.return_value = make_dzen_html()
        title, content = article.dzen_parser("https://example.com")

        assert title == "Тестовая статья Дзена"
        assert content == "Первый абзац статьи Дзена.\n\nВторой абзац статьи Дзена.\n\nЗаключительная мысль."
        mock_fetch.assert_called_once_with("https://example.com")


def test_article_fetch(tmp_path, monkeypatch):
    with patch("worker.tasks.article.update_status") as mock_status:
        fake_dzen = MagicMock()
        fake_pikabu = MagicMock()
        fake_habr = MagicMock()

        fake_habr.return_value = ("test title", "test content")

        monkeypatch.setattr(article, "ARTICLE_PARSERS", {
            "dzen": fake_dzen,
            "pikabu": fake_pikabu,
            "habr": fake_habr
        })
        monkeypatch.setattr(article, "TMP_DIR", tmp_path)
        context = ArticleContext(
            context_type = "article",
            uuid = "test-uuid",
            user_id = 123,
            title="test title",
            description=None,
            platform="habr",
            platform_id="https://habr.com",
            article_path=str(tmp_path / "test-uuid.txt"),
        )

        actual_context = article.article_fetch.run(123, "test-uuid", "https://habr.com", "habr")

        mock_status.assert_called_once_with("test-uuid", TaskStatus.downloading)
        fake_dzen.assert_not_called()
        fake_pikabu.assert_not_called()
        fake_habr.assert_called_once_with("https://habr.com")
        assert (tmp_path / "test-uuid.txt").exists()
        assert (tmp_path / "test-uuid.txt").read_text() == "test content"
        assert context == ArticleContext(**actual_context)

