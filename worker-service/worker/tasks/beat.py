import time
from pathlib import Path

from celery import shared_task

CACHE_DIR = Path("/cache")
TRANSCRIPTS_DIR = CACHE_DIR / "transcripts"
ARTICLES_DIR = CACHE_DIR / "articles"


def cleanup_directory(directory: Path, ttl: int):
    for path in directory.glob("*"):
        if time.time() - path.stat().st_atime > ttl:
            path.unlink(missing_ok=True)


@shared_task(name="cache.cleanup")
def cleanup():
    cleanup_directory(TRANSCRIPTS_DIR, 120)
    cleanup_directory(ARTICLES_DIR, 120)
