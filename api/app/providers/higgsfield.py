"""Нативный провайдер Higgsfield.

ЗАГЛУШКА Фазы 0. Точные пути/поля подтверждаем чек-листом по cloud.higgsfield.ai
(см. README, Трек A). Структура запроса — единый POST /v1/generations с Bearer.
Пока доступ к API не подтверждён, методы бросают NotImplementedError, но
сигнатуры и слой абстракции уже на месте.
"""
import httpx

from ..config import settings
from .base import JobHandle, JobResult, VideoProvider


class HiggsfieldProvider(VideoProvider):
    name = "higgsfield"

    def __init__(self) -> None:
        self._client = httpx.Client(
            base_url=settings.higgsfield_base_url,
            headers={"Authorization": f"Bearer {settings.higgsfield_api_key}"},
            timeout=60,
        )

    def _create(self, payload: dict) -> JobHandle:
        # TODO: подтвердить путь и схему по чек-листу Трека A
        resp = self._client.post("/v1/generations", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return JobHandle(external_job_id=data.get("id", ""), raw=data)

    def text_to_image(self, prompt: str, **kwargs) -> JobHandle:
        return self._create({"task": "text-to-image", "prompt": prompt, **kwargs})

    def image_to_video(self, image_url, prompt, camera=None, **kwargs) -> JobHandle:
        payload = {"task": "image-to-video", "image_url": image_url, "prompt": prompt}
        if camera:
            payload["camera"] = camera        # пресет движения + сила
        payload.update(kwargs)
        return self._create(payload)

    def lipsync(self, image_url, audio_url, **kwargs) -> JobHandle:
        return self._create({
            "task": "speak", "image_url": image_url, "audio_url": audio_url, **kwargs,
        })

    def poll_job(self, external_job_id: str) -> JobResult:
        resp = self._client.get(f"/v1/generations/{external_job_id}")
        resp.raise_for_status()
        data = resp.json()
        return JobResult(
            status=data.get("status", "running"),
            result_url=data.get("result_url"),
            raw=data,
        )
