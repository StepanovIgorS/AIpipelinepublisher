from celery import Celery
import os
from worker.cache import Cache

REDIS_URL = os.getenv('REDIS_URL')

celery_app = Celery(
    'worker_pipeline',
    broker=REDIS_URL,
    backend=REDIS_URL
)
Cache.init()
celery_app.conf.beat_schedule = {
    "cleanup-cache": {
        "task": "cache.cleanup",
        "schedule": 120.0,
    }
}
celery_app.autodiscover_tasks(["worker.tasks"])