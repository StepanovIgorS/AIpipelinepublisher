from worker.models import Context, VideoContext, ArticleContext
import requests
from worker.enums import TaskStatus
from worker.notifier import TelegramNotifier
import os


INTERNAL_SECRET = os.getenv("INTERNAL_SECRET") or ""
error_text = "😔 Упс! Не удалось распознать эту ссылку.\n\nПроверь, что ссылка:\n\n* 🔗 ведет на YouTube или статью в интернете;\n* 🌐 доступна без ограничений;\n* 📋 скопирована полностью, без лишних символов.\n\nПопробуй отправить ссылку еще раз — и я сразу подготовлю красивую выжимку, оформлю пост в нужном стиле и отправлю его в канал. 🚀"

def get_context_from_dict(ctx: dict) -> Context:
    if ctx.get("context_type") == "video":
        return VideoContext(**ctx)
    if ctx.get("context_type") == "article":
        return ArticleContext(**ctx)
    raise ValueError("Invalid context type")


def fail_task(chat, uuid, reason):
    requests.post(f"http://api-service:8000/internal/status/{uuid}",
                  headers={"X-Internal-Token": INTERNAL_SECRET},
                  json={"status": TaskStatus.error, "error": reason})
    TelegramNotifier.send_message(user_id=chat, text=error_text)


def complete(ctx: Context):
    if isinstance(ctx, VideoContext):
        if ctx.transcription_path:
            os.remove(ctx.transcription_path)
        if ctx.audio_path:
            os.remove(ctx.audio_path)
    requests.post(f"http://api-service:8000/internal/complete/{ctx.uuid}", headers={"X-Internal-Token": INTERNAL_SECRET}, timeout=5)

def update_status(uuid: str, status: TaskStatus, error: str | None = None):
    if error:
        requests.post(f"http://api-service:8000/internal/status/{uuid}",
                      headers={"X-Internal-Token": INTERNAL_SECRET},
                      json={"status": TaskStatus.error, "error": error}, timeout=5)
    else:
        requests.post(f"http://api-service:8000/internal/status/{uuid}",
                      headers={"X-Internal-Token": INTERNAL_SECRET},
                      json={"status": status}, timeout=5)