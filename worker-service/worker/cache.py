import json
import logging
import time
from dataclasses import asdict
from pathlib import Path

from worker.models import VideoCache, VideoContext

CACHE_DIR = Path("/cache")
TRANSCRIPTS_DIR = CACHE_DIR / "transcripts"
ARTICLES_DIR = CACHE_DIR / "articles"

logger = logging.getLogger(__name__)


class Cache:
    @staticmethod
    def init():
        for directory in (CACHE_DIR, TRANSCRIPTS_DIR, ARTICLES_DIR):
            directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def save_transcription(ctx: VideoContext, transcription: str):
        path = TRANSCRIPTS_DIR / ctx.platform_id
        cache = VideoCache(
            platform_id=ctx.platform_id,
            title=ctx.title,
            description=ctx.description,
            transcription=transcription,
        )
        serialized = json.dumps(asdict(cache))
        path.write_text(serialized)

    @staticmethod
    def get_transcription(platform_id: str) -> VideoCache | None:
        path = TRANSCRIPTS_DIR / platform_id
        if path.exists():
            serialized = path.read_text()
            return VideoCache(**json.loads(serialized))
        return None

    @staticmethod
    def cleanup_directory(directory: Path, ttl: int):
        logger.info("Cleaning up directory: %s", directory)
        for path in directory.glob("*"):
            if time.time() - path.stat().st_atime > ttl:
                logger.debug("Cache cleanup: Removing file: %s", path)
                path.unlink(missing_ok=True)
