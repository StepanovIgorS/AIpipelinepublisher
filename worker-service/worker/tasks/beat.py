import logging
from worker.cache import Cache, TRANSCRIPTS_DIR, ARTICLES_DIR

from celery import shared_task

logger = logging.getLogger(__name__)

@shared_task(name="cache.cleanup")
def cleanup():
    Cache.cleanup_directory(TRANSCRIPTS_DIR, 120)
    Cache.cleanup_directory(ARTICLES_DIR, 120)
