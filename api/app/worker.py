"""Celery — очередь длинных задач генерации.

Фаза 0: только каркас + healthcheck-задача. Реальные задачи генерации
(text_to_image, image_to_video, lipsync + запись версий Asset) — Фазы 2–4.
"""
from celery import Celery

from .config import settings

celery_app = Celery("videoai", broker=settings.redis_url, backend=settings.redis_url)


@celery_app.task
def ping() -> str:
    return "pong"
