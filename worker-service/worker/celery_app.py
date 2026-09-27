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
celery_app.autodiscover_tasks(["worker.tasks"])