"""Нативный провайдер Higgsfield через официальный SDK (higgsfield-client).

Auth: SyncClient шлёт заголовок `Authorization: Key <api_key>`; ключ формата
"key:secret". application — путь эндпоинта (/v1/text2image/soul и т.д.).
subscribe() блокирующе поллит до Completed и возвращает финальный JSON.

Точная схема arguments/результата подтверждается пробником scripts/probe_higgsfield.py
на реальном ключе — при расхождении правится только этот файл.
"""
import os

from higgsfield_client import SyncClient

from ..config import settings
from .base import GenResult, VideoProvider


def extract_url(result) -> str | None:
    """Достаёт URL сгенерированного ассета из ответа (форма уточняется пробником)."""
    if not isinstance(result, dict):
        return None
    for key in ("images", "videos", "outputs", "results"):
        items = result.get(key)
        if isinstance(items, list) and items:
            first = items[0]
            if isinstance(first, dict):
                return first.get("url") or first.get("uri")
            if isinstance(first, str):
                return first
    return result.get("url") or result.get("result_url")


# Соотношение сторон → width_and_height Soul (1536x1536 подтверждено; остальные — по той же сетке).
# Допустимые Soul значения (валидатор 26.10.2026): 2048x1152, 1152x2048, 1536x1536, 2048x1536, 1536x2048,
# 2016x1344, 1344x2016, 1696x960, 960x1696, 1536x1152, 1152x1536, 1632x1088, 1088x1632, 1680x1120, 1120x1680, 2048x2048
_AR_TO_WH = {"16:9": "2048x1152", "9:16": "1152x2048", "1:1": "1536x1536", "4:5": "1152x1536",
             "4:3": "2048x1536", "21:9": "2016x1344"}


class HiggsfieldProvider(VideoProvider):
    name = "higgsfield"

    def __init__(self) -> None:
        self._client = SyncClient(
            base_url=settings.higgsfield_base_url,
            api_key=(settings.higgsfield_api_key or None),
        )

    def _ensure_public(self, path_or_url: str) -> str:
        """Higgsfield не видит localhost → локальный файл заливаем через SDK."""
        if path_or_url.startswith(("http://", "https://")):
            return path_or_url
        if os.path.exists(path_or_url):
            return self._client.upload_file(path_or_url)
        return path_or_url

    def generate_image(
        self,
        prompt: str,
        *,
        soul_id: str | None = None,
        width_and_height: str = "1536x1536",
        quality: str = "1080p",
        batch_size: int = 1,
        seed: int | None = None,
        model: str | None = None,
        aspect_ratio: str | None = None,
        resolution: str | None = None,
        image_urls: list[str] | None = None,
        **kwargs,
    ) -> GenResult:
        if aspect_ratio in _AR_TO_WH:
            width_and_height = _AR_TO_WH[aspect_ratio]
        # model/resolution/image_urls — общий интерфейс (Krea); Soul их не принимает → игнорируем.
        # Подтверждённая схема Soul: тело = {"params": {...}}, width_and_height обязателен.
        params = {
            "prompt": prompt,
            "width_and_height": width_and_height,
            "quality": quality,
            "batch_size": batch_size,
        }
        if seed is not None:
            params["seed"] = seed
        if soul_id:
            params["soul_id"] = soul_id  # точное имя поля Soul ID уточним при обучении лица
        result = self._client.subscribe(settings.soul_application, {"params": params})
        return GenResult(url=extract_url(result), raw=result)

    def image_to_video(self, image_url, prompt, *, camera=None, **kwargs) -> GenResult:
        # Схема DoP уточняется на Фазе 4 (та же обёртка params).
        # end_image/reference_images/duration/model и т.п. — поля общего интерфейса (Krea), DoP их не знает.
        params = {"input_image_url": self._ensure_public(image_url), "prompt": prompt}
        if camera:
            params.update(camera)
        result = self._client.subscribe(settings.dop_application, {"params": params})
        return GenResult(url=extract_url(result), raw=result)

    def lipsync(self, image_url, audio_url, **kwargs) -> GenResult:
        # Схема Speak уточняется на Фазе 4.
        params = {
            "input_image_url": self._ensure_public(image_url),
            "audio_url": self._ensure_public(audio_url),
        }
        result = self._client.subscribe(settings.speak_application, {"params": params})
        return GenResult(url=extract_url(result), raw=result)
