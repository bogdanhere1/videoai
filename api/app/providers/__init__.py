"""Слой-абстракция провайдера генерации.

Позволяет переключаться между нативным Higgsfield и реселлерами
(Segmind / fal.ai / eachlabs) без изменения остального кода — по env VIDEO_PROVIDER.
"""
from ..config import settings
from .base import VideoProvider
from .higgsfield import HiggsfieldProvider


def get_video_provider() -> VideoProvider:
    provider = settings.video_provider
    if provider in ("native", "higgsfield"):
        return HiggsfieldProvider()
    # TODO Фаза 0+: SegmindProvider, FalProvider, EachlabsProvider
    raise ValueError(f"Unknown VIDEO_PROVIDER: {provider}")
