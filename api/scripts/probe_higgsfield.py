"""Эмпирическая проверка реального вызова Higgsfield Soul.

Запуск из папки api/ (чтобы прочитался api/.env):
    .venv/Scripts/python -m scripts.probe_higgsfield

Ключ НЕ печатается. Скрипт делает одну генерацию картинки и показывает
структуру ответа, чтобы подтвердить схему arguments/результата для провайдера.
"""
import json
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows-консоль по умолчанию cp1251
except Exception:
    pass

from app.config import settings
from higgsfield_client import SyncClient


def main() -> int:
    key = settings.higgsfield_api_key.strip()
    if not key:
        print("[!] HIGGSFIELD_API_KEY пуст в api/.env — впиши ключ и повтори.")
        return 1
    has_secret = ":" in key
    print(f"[i] key present: yes | length={len(key)} | contains ':' (key:secret) = {has_secret}")
    print(f"[i] base_url = {settings.higgsfield_base_url}")
    print(f"[i] application = {settings.soul_application}")

    client = SyncClient(base_url=settings.higgsfield_base_url, api_key=key)
    args = {"params": {
        "prompt": "a cozy coffee cup on a wooden table, morning light, photorealistic",
        "width_and_height": "1536x1536",
        "quality": "1080p",
        "batch_size": 1,
        "seed": 42,
    }}
    print(f"[>] subscribe({settings.soul_application!r}, {args})")

    try:
        result = client.subscribe(settings.soul_application, args)
    except Exception as e:
        print(f"[x] ОШИБКА вызова: {type(e).__name__}: {e}")
        print("    -> вероятно неверный формат ключа (нужен key:secret), путь application или схема arguments.")
        return 2

    print("[✓] Готово. Ключи ответа:", list(result.keys()) if isinstance(result, dict) else type(result))
    print("[dump] (обрезано до 1500 симв):")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:1500])

    from app.providers.higgsfield import extract_url
    print("[url] extract_url →", extract_url(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
