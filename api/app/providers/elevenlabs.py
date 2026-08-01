"""ElevenLabs: STT (Scribe) для голосового ввода идеи, TTS/SFX — на Фазах 2-4."""
import httpx

from ..config import settings

_BASE = "https://api.elevenlabs.io/v1"


def transcribe(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    """Голос → текст через Scribe. Используется для голосового ввода идеи."""
    if not settings.elevenlabs_api_key:
        raise RuntimeError("ELEVENLABS_API_KEY не задан в .env")
    resp = httpx.post(
        f"{_BASE}/speech-to-text",
        headers={"xi-api-key": settings.elevenlabs_api_key},
        data={"model_id": "scribe_v1"},
        files={"file": (filename, audio_bytes)},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json().get("text", "")


def tts(text: str, voice_id: str, **kwargs) -> bytes:
    """Текст → голос (MP3). Понадобится на Фазе 4 (озвучка + вход для липсинка)."""
    raise NotImplementedError("TTS подключим на Фазе 4")
