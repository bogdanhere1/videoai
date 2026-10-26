"""Слой-абстракция провайдера генерации.

VIDEO_PROVIDER: auto — Krea, если задан KREA_API_KEY, иначе Higgsfield; krea; native/higgsfield.
Per-stage переопределение (StageSetting) делается в main._gen_ctx.
"""
from ..config import settings
from .base import VideoProvider
from .higgsfield import HiggsfieldProvider
from .krea import KreaProvider


def default_provider_name() -> str:
    p = (settings.video_provider or "auto").lower()
    if p == "auto":
        return "krea" if settings.krea_api_key.strip() else "higgsfield"
    if p in ("native", "higgsfield"):
        return "higgsfield"
    return p


def get_video_provider(name: str | None = None) -> VideoProvider:
    provider = (name or default_provider_name()).lower()
    if provider == "krea":
        return KreaProvider()
    if provider in ("native", "higgsfield"):
        return HiggsfieldProvider()
    raise ValueError(f"Unknown VIDEO_PROVIDER: {provider}")
