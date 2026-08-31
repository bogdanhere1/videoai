"""Локальное хранилище ассетов.

URL результатов Higgsfield живёт ~1 час → скачиваем сразу к себе.
Локально: папка media/, отдаётся FastAPI по /media. На VPS заменим на MinIO/S3.
"""
import os
import uuid

import httpx

from .config import settings


def _ensure_dir() -> None:
    os.makedirs(settings.media_dir, exist_ok=True)


def save_from_url(url: str, ext: str = ".png") -> str:
    _ensure_dir()
    r = httpx.get(url, timeout=120, follow_redirects=True)
    r.raise_for_status()
    name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(settings.media_dir, name), "wb") as f:
        f.write(r.content)
    return f"/media/{name}"


def save_bytes(data: bytes, ext: str) -> str:
    _ensure_dir()
    name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(settings.media_dir, name), "wb") as f:
        f.write(data)
    return f"/media/{name}"
