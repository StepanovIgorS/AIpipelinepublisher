import logging

from celery import shared_task

from worker import cache

logger = logging.getLogger(__name__)


@shared_task(name="cache.cleanup")
def cleanup():
    cache.Cache.cleanup_directory(cache.TRANSCRIPTS_DIR, 120)
    cache.Cache.cleanup_directory(cache.ARTICLES_DIR, 120)
