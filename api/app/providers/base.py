"""Единый интерфейс провайдера генерации.

Фаза 2: синхронно через subscribe() (SDK сам поллит до Completed).
Для видео на Фазе 4 добавим submit()+webhook для параллелизма.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class GenResult:
    url: str | None
    raw: dict = field(default_factory=dict)


class VideoProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate_image(self, prompt: str, *, soul_id: str | None = None, **kwargs) -> GenResult:
        """Концепт-статика (Higgsfield Soul). soul_id — для консистентности персонажа."""

    @abstractmethod
    def image_to_video(self, image_url: str, prompt: str, *, camera: dict | None = None, **kwargs) -> GenResult:
        """Оживление кадра с контролем камеры (DoP)."""

    @abstractmethod
    def lipsync(self, image_url: str, audio_url: str, **kwargs) -> GenResult:
        """Говорящий аватар (Speak v2). audio_url — готовый MP3 из ElevenLabs."""
