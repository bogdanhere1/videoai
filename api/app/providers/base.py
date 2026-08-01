"""Единый интерфейс провайдера генерации.

Любой бэкенд (нативный Higgsfield или реселлер) реализует эти методы.
Все методы возвращают external_job_id — задачи асинхронные, результат
забираем через poll_job() или webhook.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class JobHandle:
    external_job_id: str
    raw: dict


@dataclass
class JobResult:
    status: str          # queued|running|done|failed
    result_url: str | None
    raw: dict


class VideoProvider(ABC):
    name: str = "base"

    @abstractmethod
    def text_to_image(self, prompt: str, **kwargs) -> JobHandle:
        """Концепт-статика (Higgsfield Soul)."""

    @abstractmethod
    def image_to_video(self, image_url: str, prompt: str, camera: dict | None = None, **kwargs) -> JobHandle:
        """Оживление кадра с контролем камеры."""

    @abstractmethod
    def lipsync(self, image_url: str, audio_url: str, **kwargs) -> JobHandle:
        """Говорящий аватар (Higgsfield Speak v2). audio_url — готовый MP3 из ElevenLabs."""

    @abstractmethod
    def poll_job(self, external_job_id: str) -> JobResult:
        """Опрос статуса задачи."""
