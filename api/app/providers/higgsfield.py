"""Нативный провайдер Higgsfield через официальный SDK (higgsfield-client).

Auth: SyncClient шлёт заголовок `Authorization: Key <api_key>`; ключ формата
"key:secret". application — путь эндпоинта (/v1/text2image/soul и т.д.).
subscribe() блокирующе поллит до Completed и возвращает финальный JSON.

Точная схема arguments/результата подтверждается пробником scripts/probe_higgsfield.py
на реальном ключе — при расхождении правится только этот файл.
"""
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


class HiggsfieldProvider(VideoProvider):
    name = "higgsfield"

    def __init__(self) -> None:
        self._client = SyncClient(
            base_url=settings.higgsfield_base_url,
            api_key=(settings.higgsfield_api_key or None),
        )

    def generate_image(
        self,
        prompt: str,
        *,
        soul_id: str | None = None,
        width_and_height: str = "1536x1536",
        quality: str = "1080p",
        batch_size: int = 1,
        seed: int | None = None,
        **kwargs,
    ) -> GenResult:
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
        params.update(kwargs)
        result = self._client.subscribe(settings.soul_application, {"params": params})
        return GenResult(url=extract_url(result), raw=result)

    def image_to_video(self, image_url, prompt, *, camera=None, **kwargs) -> GenResult:
        # Схема DoP уточняется на Фазе 4 (та же обёртка params).
        params = {"input_image_url": image_url, "prompt": prompt}
        if camera:
            params.update(camera)
        params.update(kwargs)
        result = self._client.subscribe(settings.dop_application, {"params": params})
        return GenResult(url=extract_url(result), raw=result)

    def lipsync(self, image_url, audio_url, **kwargs) -> GenResult:
        # Схема Speak уточняется на Фазе 4.
        params = {"input_image_url": image_url, "audio_url": audio_url, **kwargs}
        result = self._client.subscribe(settings.speak_application, {"params": params})
        return GenResult(url=extract_url(result), raw=result)
