"""ElevenLabs — весь звук пайплайна: STT (Scribe), TTS (голос), SFX, музыка (music_v2).

Точные эндпоинты/схемы подтверждаются пробником scripts/probe_elevenlabs.py на живом ключе.
"""
import httpx

from ..config import settings

_BASE = "https://api.elevenlabs.io/v1"


def _headers(json: bool = False) -> dict:
    if not settings.elevenlabs_api_key:
        raise RuntimeError("ELEVENLABS_API_KEY не задан в .env")
    h = {"xi-api-key": settings.elevenlabs_api_key}
    if json:
        h["Content-Type"] = "application/json"
    return h


def transcribe(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    """Голос → текст (Scribe) — голосовой ввод идеи."""
    resp = httpx.post(
        f"{_BASE}/speech-to-text",
        headers=_headers(),
        data={"model_id": "scribe_v1"},
        files={"file": (filename, audio_bytes)},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json().get("text", "")


def list_voices() -> list[dict]:
    resp = httpx.get(f"{_BASE}/voices", headers=_headers(), timeout=30)
    resp.raise_for_status()
    return [
        {"voice_id": v.get("voice_id"), "name": v.get("name"), "labels": v.get("labels", {})}
        for v in resp.json().get("voices", [])
    ]


def tts(text: str, voice_id: str, model_id: str = "eleven_multilingual_v2") -> bytes:
    """Текст → голос (MP3). Используется как озвучка и как вход для липсинка."""
    resp = httpx.post(
        f"{_BASE}/text-to-speech/{voice_id}",
        headers=_headers(json=True),
        json={"text": text, "model_id": model_id},
        timeout=180,
    )
    resp.raise_for_status()
    return resp.content


def sound_effect(prompt: str, duration_seconds: float | None = None) -> bytes:
    body: dict = {"text": prompt}
    if duration_seconds:
        body["duration_seconds"] = duration_seconds
    resp = httpx.post(
        f"{_BASE}/sound-generation", headers=_headers(json=True), json=body, timeout=180
    )
    resp.raise_for_status()
    return resp.content


def music(prompt: str, length_ms: int = 10000) -> bytes:
    resp = httpx.post(
        f"{_BASE}/music",
        headers=_headers(json=True),
        json={"prompt": prompt, "music_length_ms": length_ms, "model_id": "music_v2"},
        timeout=240,
    )
    resp.raise_for_status()
    return resp.content
