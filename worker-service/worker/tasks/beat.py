import time
import logging
from pathlib import Path

from celery import shared_task

logger = logging.getLogger(__name__)

CACHE_DIR = Path("/cache")
TRANSCRIPTS_DIR = CACHE_DIR / "transcripts"
ARTICLES_DIR = CACHE_DIR / "articles"


def cleanup_directory(directory: Path, ttl: int):
    logger.info("Cleaning up directory: %s", directory)
    for path in directory.glob("*"):
        if time.time() - path.stat().st_atime > ttl:
            logger.debug("Cache cleanup: Removing file: %s", path)
            path.unlink(missing_ok=True)


@shared_task(name="cache.cleanup")
def cleanup():
    cleanup_directory(TRANSCRIPTS_DIR, 120)
    cleanup_directory(ARTICLES_DIR, 120)
