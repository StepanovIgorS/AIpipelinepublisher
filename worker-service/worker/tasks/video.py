import os
from dataclasses import asdict

import yt_dlp
from celery import shared_task
from celery.signals import worker_shutdown
from yt_dlp.utils import DownloadError

from worker.cache import Cache
from worker.enums import TaskStatus
from worker.models import VideoContext
from worker.notifier import TelegramNotifier
from worker.utils import fail_task, update_status

ydl_opts = {
    "noplaylist": True,
    "format": "bestaudio/best",
}


def get_download_options(uuid: str) -> dict:
    return {
        "noplaylist": True,
        "format": "m4a/bestaudio/best",
        "outtmpl": f"/tmp/{uuid}.%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
    }


@shared_task(name="video.download")
def download_video(user_id: int, uuid: str, url: str, platform: str, is_premium: bool):
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        update_status(uuid, TaskStatus.downloading)
        try:
            info = ydl.extract_info(url, download=False)
        except DownloadError as e:
            fail_task(user_id, uuid, str(e))
            raise
        duration = info.get("duration")
        if not duration:
            fail_task(user_id, uuid, "Invalid link (duration)")
            raise DownloadError("Invalid link (duration)")
        if not is_premium and duration > 1800:  # 30 minutes
            fail_task(
                user_id,
                uuid,
                "Invalid link (duration)",
                "Ты не можешь скачивать видео длиннее 30 минут без премиум подписки.",
            )
            raise DownloadError("Invalid link (duration)")
        if cached_ctx := Cache.get_transcription(info.get("id", "")):
            transcription_path = f"/tmp/{uuid}.txt"
            with open(transcription_path, "w") as f:
                f.write(cached_ctx.transcription)
            ctx = VideoContext(
                context_type="video",
                uuid=uuid,
                user_id=user_id,
                platform=platform,
                platform_id=cached_ctx.platform_id,
                title=cached_ctx.title,
                description=cached_ctx.description,
                transcription_path=transcription_path,
                audio_path="",
            )
            return asdict(ctx)
    with yt_dlp.YoutubeDL(get_download_options(uuid)) as ydl:
        info = ydl.extract_info(url, download=True)
        downloads = info.get("requested_downloads", [{}])
        path = downloads[0].get("filepath")
        if not path:
            fail_task(user_id, uuid, "Invalid link (requested_downloads)")
            raise DownloadError("Invalid link (requested_downloads)")
        ctx = VideoContext(
            context_type="video",
            uuid=uuid,
            user_id=user_id,
            platform_id=info.get("id"),
            platform=platform,
            title=info.get("title", ""),
            description=info.get("description", ""),
            audio_path=path,
        )
        return asdict(ctx)


@worker_shutdown.connect
def shutdown(**kwargs):
    try:
        TelegramNotifier.shutdown()
    except Exception:
        pass


"""

Когда MVP готов, начинаешь делать его "боевым":
добавить секрет к webhook

логирование;
retry;
таймауты;
обработка ошибок;
health;
request_id.

То есть ты ничего не меняешь в бизнес-логике, а повышаешь надежность.

Этап 3. Масштабирование

Если захочешь впечатлить работодателя:

Prometheus;
Grafana;
метрики Celery;
мониторинг Redis;
Docker Healthcheck;
CI/CD (GitHub Actions);
тесты;
линтеры;
pre-commit.

"""
