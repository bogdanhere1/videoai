"""Пробник Krea API на реальном токене. Запуск из api/:  .venv/Scripts/python -m scripts.probe_krea [video]

Ключ не печатается. Делает одну дешёвую картинку (≈22 CU) и показывает структуру job;
с аргументом video — ещё и 4-секундный draft-ролик из этой картинки.
"""
import json
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.config import settings
from app.providers.krea import KreaProvider


def main() -> int:
    key = settings.krea_api_key.strip()
    if not key:
        print("[!] KREA_API_KEY пуст в api/.env — создай токен на krea.ai/settings/api-tokens и впиши.")
        return 1
    print(f"[i] key present: yes | length={len(key)} | base={settings.krea_base_url}")
    p = KreaProvider()
    print(f"[>] image via {p.image_model}")
    res = p.generate_image("a cozy coffee cup on a wooden table, morning light, photorealistic",
                           aspect_ratio="16:9", resolution="1K")
    print("[<] job:", json.dumps(res.raw, ensure_ascii=False)[:600])
    print("[<] url:", res.url)
    if not res.url:
        return 2
    if len(sys.argv) > 1 and sys.argv[1] == "video":
        print(f"[>] video via {p.video_model} (draft, 4s)")
        v = p.image_to_video(res.url, "Slow push in, steam rising from the cup, soft morning light, realtime",
                             duration=4, draft=True)
        print("[<] job:", json.dumps(v.raw, ensure_ascii=False)[:600])
        print("[<] url:", v.url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
