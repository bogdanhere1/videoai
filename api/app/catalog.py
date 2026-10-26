"""Каталог моделей для настроек по этапам (курируемая выборка из Krea public API, 26.10.2026).

Фронт показывает его в выпадающих списках; любой другой id можно вписать руками.
"""

PROVIDERS = [
    {"id": "", "name": "по умолчанию (из .env)"},
    {"id": "krea", "name": "Krea (api.krea.ai) — картинки, видео, музыка"},
    {"id": "higgsfield", "name": "Higgsfield (Soul / DoP / Speak)"},
    {"id": "elevenlabs", "name": "ElevenLabs (голос / SFX / музыка)"},
    {"id": "gemini", "name": "Gemini (LLM)"},
    {"id": "custom", "name": "Другой (base URL + ключ)"},
]

IMAGE_MODELS = [
    {"id": "google/nano-banana-2.1", "name": "Nano Banana 2.1 — быстрый, pro-качество, референсы (default)"},
    {"id": "google/nano-banana-pro", "name": "Nano Banana Pro — максимальный интеллект"},
    {"id": "bfl/flux-2-klein", "name": "Flux 2 Klein — быстрый, seed + до 4 референсов"},
    {"id": "krea/krea-3", "name": "Krea 3 — генерация и правка"},
    {"id": "bytedance/seedream-5-pro", "name": "Seedream 5 Pro — фотореализм, точные правки"},
    {"id": "krea/krea-2/large", "name": "Krea 2 Large — экспрессивный фотореализм"},
    {"id": "ideogram/ideogram-4.5", "name": "Ideogram 4.5 — текст в кадре, до 5 референсов"},
    {"id": "runway/gen-4-image", "name": "Runway Gen-4 Image — кино-стилистика, референсы"},
]

VIDEO_MODELS = [
    {"id": "bytedance/seedance-2-5", "name": "Seedance 2.5 — до 30с, звук, старт+финал, 1080p, draft (default)"},
    {"id": "bytedance/seedance-2-fast", "name": "Seedance 2.0 Fast — до 15с, дешевле"},
    {"id": "bytedance/seedance-2-mini", "name": "Seedance 2.0 Mini — самый дешёвый"},
    {"id": "google/veo-3.1", "name": "Veo 3.1 — топ-качество со звуком"},
    {"id": "google/veo-3.1-fast", "name": "Veo 3.1 Fast — быстрее/дешевле"},
    {"id": "kling/kling-3.0", "name": "Kling 3.0 — звук, до 15с"},
    {"id": "kling/kling-4", "name": "Kling 4.0 — до 30с 1080p"},
    {"id": "minimax/hailuo-2.3", "name": "Hailuo 2.3 — динамичное движение"},
    {"id": "runway/gen-4.5", "name": "Runway Gen-4.5 — text-to-video"},
    {"id": "alibaba/wan-3.0", "name": "Wan 3.0 — до 30с, звук, референсы"},
]

AUDIO_MODELS = [
    {"id": "elevenlabs/music-v2.5", "name": "ElevenLabs Music v2.5 (через Krea) — музыка (default)"},
    {"id": "elevenlabs/music-v2", "name": "ElevenLabs Music v2 (через Krea)"},
    {"id": "elevenlabs/tts", "name": "ElevenLabs TTS (через Krea)"},
    {"id": "bytedance/seed-audio-1.0", "name": "Seed Audio 1.0 — речь, диалог, саунд-дизайн"},
]

LLM_MODELS = [
    {"id": "gemini-3.1-flash-lite", "name": "Gemini 3.1 Flash Lite (default, работает с ключом AQ.…)"},
    {"id": "gemini-3.1-flash", "name": "Gemini 3.1 Flash"},
    {"id": "gemini-3.1-pro", "name": "Gemini 3.1 Pro"},
]

# Какая категория моделей уместна на этапе
STAGE_CATEGORY = {"idea": "llm", "script": "llm", "style": "image", "storyboard": "image",
                  "shots": "video", "assembly": "none"}

ASPECTS = ["16:9", "9:16", "1:1", "4:5", "4:3", "21:9"]
IMAGE_RES = ["1K", "2K"]
VIDEO_QUALITY = ["draft", "480p", "720p", "1080p"]
PROJECT_KINDS = [
    {"id": "ad", "name": "Рекламный ролик"},
    {"id": "social", "name": "Соцсети / Reels / Shorts"},
    {"id": "explainer", "name": "Объясняющий / продуктовый"},
    {"id": "story", "name": "История / короткометражка"},
    {"id": "music", "name": "Музыкальный клип"},
    {"id": "intro", "name": "Заставка / интро"},
]
FORMAT_DEFAULTS = {"aspect_ratio": "16:9", "resolution": "1K", "video_quality": "720p",
                   "shot_duration": 5, "kind": "ad", "target_seconds": 30}


def catalog() -> dict:
    return {
        "providers": PROVIDERS, "image": IMAGE_MODELS, "video": VIDEO_MODELS,
        "audio": AUDIO_MODELS, "llm": LLM_MODELS, "stage_category": STAGE_CATEGORY,
        "aspects": ASPECTS, "image_res": IMAGE_RES, "video_quality": VIDEO_QUALITY,
        "project_kinds": PROJECT_KINDS, "format_defaults": FORMAT_DEFAULTS,
    }
