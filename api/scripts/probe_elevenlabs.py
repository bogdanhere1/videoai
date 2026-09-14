"""Проверка ElevenLabs вживую: voices / TTS / SFX / music.

Запуск из api/:  .venv/Scripts/python -m scripts.probe_elevenlabs
Сохраняет сэмплы в media/ и печатает размеры. Ключ не печатается.
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.providers import elevenlabs as el
from app import storage


def _try(label, fn):
    try:
        return fn()
    except Exception as e:
        print(f"[x] {label}: {type(e).__name__}: {str(e)[:300]}")
        return None


def main() -> int:
    print("[i] voices…")
    voices = _try("voices", el.list_voices)
    if voices:
        print(f"[✓] голосов: {len(voices)}. Первые:", [v["name"] for v in voices[:5]])
    vid = voices[0]["voice_id"] if voices else "21m00Tcm4TlvDq8ikWAM"

    print("[i] TTS…")
    audio = _try("tts", lambda: el.tts("Утро начинается с чашки кофе.", vid))
    if audio:
        print("[✓] TTS сохранён:", storage.save_bytes(audio, ".mp3"), f"({len(audio)} байт)")

    print("[i] SFX…")
    sfx = _try("sfx", lambda: el.sound_effect("coffee machine steam hiss, cozy cafe ambience", 4))
    if sfx:
        print("[✓] SFX сохранён:", storage.save_bytes(sfx, ".mp3"), f"({len(sfx)} байт)")

    print("[i] music…")
    mus = _try("music", lambda: el.music("calm warm morning lo-fi, soft piano", 10000))
    if mus:
        print("[✓] music сохранён:", storage.save_bytes(mus, ".mp3"), f"({len(mus)} байт)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
