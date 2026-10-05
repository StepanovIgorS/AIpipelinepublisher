from celery import shared_task
from pathlib import Path
from datetime import datetime

CACHE_DIR = Path("/cache")
TRANSCRIPTS_DIR = CACHE_DIR / "transcripts"
ARTICLES_DIR = CACHE_DIR / "articles"


def cleanup_directory(directory: Path, ttl: int):
    for path in directory.glob("*"):
        time_diff = datetime.now() - datetime.fromtimestamp(path.stat().st_atime)
        if time_diff.total_seconds() > ttl:
            path.unlink(missing_ok=True)


@shared_task(name="cache.cleanup")
def cleanup():
    cleanup_directory(TRANSCRIPTS_DIR, 120)
    cleanup_directory(ARTICLES_DIR, 120)