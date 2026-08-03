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

    def generate_image(self, prompt: str, *, soul_id: str | None = None, **kwargs) -> GenResult:
        args = {"prompt": prompt, **kwargs}
        if soul_id:
            args["soul_id"] = soul_id
        result = self._client.subscribe(settings.soul_application, args)
        return GenResult(url=extract_url(result), raw=result)

    def image_to_video(self, image_url, prompt, *, camera=None, **kwargs) -> GenResult:
        args = {"input_image_url": image_url, "prompt": prompt, **kwargs}
        if camera:
            args.update(camera)
        result = self._client.subscribe(settings.dop_application, args)
        return GenResult(url=extract_url(result), raw=result)

    def lipsync(self, image_url, audio_url, **kwargs) -> GenResult:
        args = {"input_image_url": image_url, "audio_url": audio_url, **kwargs}
        result = self._client.subscribe(settings.speak_application, args)
        return GenResult(url=extract_url(result), raw=result)
