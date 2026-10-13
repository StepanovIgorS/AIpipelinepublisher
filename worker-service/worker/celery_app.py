import logging
import os

from celery import Celery

from worker.cache import Cache

REDIS_URL = os.getenv("REDIS_URL")
logging.basicConfig(level=logging.INFO, force=True)

celery_app = Celery("worker_pipeline", broker=REDIS_URL, backend=REDIS_URL)
Cache.init()
celery_app.conf.beat_schedule = {
    "cleanup-cache": {
        "task": "cache.cleanup",
        "schedule": 120.0,
    }
}
celery_app.autodiscover_tasks(["worker.tasks"])
