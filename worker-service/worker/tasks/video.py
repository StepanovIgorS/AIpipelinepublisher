import logging
import os
from dataclasses import asdict
from pathlib import Path

import yt_dlp
from celery import shared_task
from celery.signals import worker_shutdown
from yt_dlp.utils import DownloadError

from worker.cache import Cache
from worker.enums import TaskStatus
from worker.models import VideoContext
from worker.notifier import TelegramNotifier
from worker.utils import fail_task, update_status

logger = logging.getLogger(__name__)

TMP_DIR = Path("/tmp")

ydl_opts = {
    "noplaylist": True,
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
}


def get_download_options(uuid: str) -> dict:
    return {
        "noplaylist": True,
        "format": "m4a/bestaudio/best",
        "outtmpl": str(TMP_DIR / f"{uuid}.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
    }


@shared_task(name="video.download")
def download_video(user_id: int, uuid: str, url: str, platform: str, is_premium: bool):
    logger.info(
        "task %s downloading video from platform %s for user %s",
        uuid,
        platform,
        user_id,
    )
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        update_status(uuid, TaskStatus.downloading)
        try:
            info = ydl.extract_info(url, download=False)
        except DownloadError as e:
            fail_task(user_id, uuid, str(e))
            logger.exception(
                "task %s got an unexpected error! for user %s", uuid, user_id
            )
            raise
        duration = info.get("duration")
        if not duration:
            fail_task(user_id, uuid, "Invalid link (duration)")
            logger.error(
                "task %s got an invalid link (duration) for user %s", uuid, user_id
            )
            raise DownloadError("Invalid link (duration)")
        if not is_premium and duration > 1800:  # 30 minutes
            fail_task(
                user_id,
                uuid,
                "Invalid link (duration)",
                "Ты не можешь скачивать видео длиннее 30 минут без премиум подписки.",
            )
            logger.warning(
                "task %s exceeds max video duration for free plan for user %s",
                uuid,
                user_id,
            )
            raise DownloadError("Invalid link (duration)")
        logger.info(
            "task %s got video info. duration: %s, user_status %s",
            uuid,
            duration,
            is_premium,
        )
        if cached_ctx := Cache.get_transcription(info.get("id", "")):
            logger.info("task %s found cached transcription for user %s", uuid, user_id)
            transcription_path = str(TMP_DIR / f"{uuid}.txt")
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
            logger.info(
                "task %s video was not download. platform %s platform_id %s returning cached transcription for user %s",
                uuid,
                platform,
                cached_ctx.platform_id,
                user_id,
            )
            return asdict(ctx)
    with yt_dlp.YoutubeDL(get_download_options(uuid)) as ydl:
        info = ydl.extract_info(url, download=True)
        downloads = info.get("requested_downloads", [{}])
        path = downloads[0].get("filepath")
        if not path:
            logger.error(
                "task %s video was not download due to invalid link for user %s url is: %s",
                uuid,
                user_id,
                url,
            )
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
        logger.info(
            "task %s video was downloaded successfully on platform %s with platform_id %s file_size %s for user %s",
            uuid,
            platform,
            ctx.platform_id,
            os.path.getsize(path),
            user_id,
        )
        return asdict(ctx)


@worker_shutdown.connect
def shutdown(**kwargs):
    try:
        TelegramNotifier.shutdown()
    except Exception:
        logger.exception("Failed to shutdown TelegramNotifier")


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
