"""Krea public API (https://api.krea.ai) — универсальный провайдер: картинка, видео, музыка, TTS.

Подтверждено живым вызовом (26.10.2026):
  POST /generate/{category}/{vendor}/{model}  body = поля схемы модели  → {"job_id", "status"}
  GET  /jobs/{job_id} → {"status": ..., "result": {"urls": [...]}}; failed → result.error
  POST /assets  multipart(file=…, description=…) → {"image_url": ...}  (локальные файлы → публичный URL)
Auth: Authorization: Bearer <token> (krea.ai/settings/api-tokens).
БИЛЛИНГ: HTTP-токен списывает с ОТДЕЛЬНОГО API-баланса (пополнение от $5 на krea.ai/app/api),
а не с compute units веб-плана. 402 = баланс пуст.
Каждая модель принимает только свои поля (additionalProperties=false) → см. MODEL_FIELDS.
"""
import mimetypes
import os
import time

import httpx

from ..config import settings
from .base import GenResult, VideoProvider

PENDING = {"backlogged", "queued", "scheduled", "processing", "sampling", "intermediate-complete"}

# Какие необязательные поля понимает модель (всё лишнее Krea отклоняет 400).
_IMG_COMMON = {"aspect_ratio", "resolution", "image_urls"}
MODEL_FIELDS: dict[str, set[str]] = {
    "google/nano-banana-2.1": _IMG_COMMON | {"thinking_level", "width", "height"},
    "google/nano-banana-pro": _IMG_COMMON | {"thinking_level"},
    "google/nano-banana-2": _IMG_COMMON,
    "google/nano-banana-flash-lite": _IMG_COMMON,
    "bfl/flux-2-klein": _IMG_COMMON | {"seed", "negative_prompt", "num_inference_steps", "cfg_scale"},
    "krea/krea-3": {"aspect_ratio", "resolution", "thinking_mode"},
    "bytedance/seedream-4": _IMG_COMMON | {"seed"},
    "bytedance/seedream-5-pro": _IMG_COMMON | {"seed"},
}
# Видео-модели: максимум длительности и допустимые разрешения.
VIDEO_LIMITS: dict[str, dict] = {
    "bytedance/seedance-2-5": {"max": 30, "res": ("480p", "720p", "1080p"), "draft": True},
    "bytedance/seedance-2": {"max": 15, "res": ("480p", "720p")},
    "bytedance/seedance-2-fast": {"max": 15, "res": ("480p", "720p")},
    "bytedance/seedance-2-mini": {"max": 15, "res": ("480p", "720p")},
}
# Ориентировочная стоимость в compute units (preflight 26.10.2026): картинка nano-banana 1K = 22,
# Seedance 2.5 720p 5с = 856 (≈171/с). Draft 480p — заметно дешевле (оценка ~1/3).
CU_IMAGE = 22
CU_VIDEO_PER_SEC = {"480p": 60, "720p": 171, "1080p": 300, "draft": 60}


class KreaError(RuntimeError):
    pass


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


class KreaProvider(VideoProvider):
    name = "krea"

    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 image_model: str | None = None, video_model: str | None = None) -> None:
        self.api_key = (api_key or settings.krea_api_key or "").strip()
        self.base_url = (base_url or settings.krea_base_url).rstrip("/")
        self.image_model = image_model or settings.krea_image_model
        self.video_model = video_model or settings.krea_video_model

    # ---- низкий уровень ----
    def _headers(self) -> dict:
        if not self.api_key:
            raise KreaError("KREA_API_KEY не задан (api/.env) — создай токен на krea.ai/settings/api-tokens")
        return {"Authorization": f"Bearer {self.api_key}"}

    def submit(self, endpoint_path: str, body: dict) -> str:
        r = httpx.post(f"{self.base_url}/generate/{endpoint_path}", headers=self._headers(),
                       json=body, timeout=60)
        if r.status_code == 402:
            raise KreaError("Krea: API-баланс пуст (402). Пополни на krea.ai/app/api — "
                            "это отдельный баланс, не compute units плана.")
        if r.status_code == 429:
            raise KreaError("Krea: достигнут лимит одновременных задач (429), подожди и повтори.")
        if r.status_code >= 400:
            raise KreaError(f"Krea {r.status_code} на {endpoint_path}: {r.text[:300]}")
        job_id = r.json().get("job_id")
        if not job_id:
            raise KreaError(f"Krea не вернул job_id: {r.text[:200]}")
        return job_id

    def job(self, job_id: str) -> dict:
        r = httpx.get(f"{self.base_url}/jobs/{job_id}", headers=self._headers(), timeout=30)
        r.raise_for_status()
        return r.json()

    def wait(self, job_id: str, timeout: float = 900, interval: float = 3.0) -> dict:
        t0 = time.time()
        delay = interval
        while True:
            j = self.job(job_id)
            st = j.get("status")
            if st == "completed":
                return j
            if st in ("failed", "cancelled"):
                err = (j.get("result") or {}).get("error") or j.get("error") or st
                raise KreaError(f"Krea job {st}: {err}")
            if time.time() - t0 > timeout:
                raise KreaError(f"Krea job {job_id} не завершился за {int(timeout)}с")
            time.sleep(delay)
            delay = min(delay * 1.3, 8.0)

    def run(self, endpoint_path: str, body: dict) -> GenResult:
        job = self.wait(self.submit(endpoint_path, body))
        urls = (job.get("result") or {}).get("urls") or []
        # Seedance может «тихо» отказать: completed без urls → это отказ фильтра, не успех.
        return GenResult(url=urls[0] if urls else None, raw=job)

    def upload(self, path: str, description: str = "studio asset") -> str:
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as fh:
            r = httpx.post(f"{self.base_url}/assets", headers=self._headers(),
                           files={"file": (os.path.basename(path), fh, mime)},
                           data={"description": description}, timeout=180)
        if r.status_code >= 400:
            raise KreaError(f"Krea upload {r.status_code}: {r.text[:200]}")
        data = r.json()
        url = data.get("image_url") or data.get("url") or data.get("video_url") or data.get("audio_url")
        if not url:
            raise KreaError(f"Krea upload: нет URL в ответе {str(data)[:200]}")
        return url

    def _ensure_public(self, path_or_url: str | None) -> str | None:
        if not path_or_url:
            return None
        if path_or_url.startswith(("http://", "https://", "data:")):
            return path_or_url
        if os.path.exists(path_or_url):
            return self.upload(path_or_url)
        return path_or_url

    # ---- картинка ----
    def generate_image(self, prompt: str, *, soul_id: str | None = None, seed: int | None = None,
                       model: str | None = None, aspect_ratio: str = "16:9", resolution: str = "1K",
                       image_urls: list[str] | None = None, **kwargs) -> GenResult:
        model = model or self.image_model
        allowed = MODEL_FIELDS.get(model, _IMG_COMMON)
        body: dict = {"prompt": prompt}
        if "aspect_ratio" in allowed and aspect_ratio:
            body["aspect_ratio"] = aspect_ratio
        if "resolution" in allowed and resolution:
            body["resolution"] = resolution
        if "seed" in allowed and seed is not None:
            body["seed"] = int(seed)
        refs = [u for u in (self._ensure_public(u) for u in (image_urls or [])) if u]
        if "image_urls" in allowed and refs:
            body["image_urls"] = refs[:4]
        for k, v in kwargs.items():
            if k in allowed and v is not None:
                body[k] = v
        return self.run(f"image/{model}", body)

    # ---- видео ----
    def _video_body(self, model: str, prompt: str, *, duration: float, aspect_ratio: str,
                    resolution: str, draft: bool, seed: int | None) -> dict:
        lim = VIDEO_LIMITS.get(model, {"max": 15, "res": ("480p", "720p")})
        if resolution not in lim["res"]:
            resolution = lim["res"][-1]
        body: dict = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration": int(_clamp(round(duration or 5), 4, lim["max"])),
            "resolution": resolution,
        }
        if draft and lim.get("draft"):
            body["draft"] = True
        if seed is not None:
            body["seed"] = int(seed)
        return body

    def image_to_video(self, image_url: str | None, prompt: str, *, camera: dict | None = None,
                       end_image: str | None = None, reference_images: list[str] | None = None,
                       reference_audios: list[str] | None = None, duration: float = 5,
                       aspect_ratio: str = "16:9", resolution: str = "720p", draft: bool = False,
                       model: str | None = None, seed: int | None = None, **kwargs) -> GenResult:
        model = model or self.video_model
        body = self._video_body(model, prompt, duration=duration, aspect_ratio=aspect_ratio,
                                resolution=resolution, draft=draft, seed=seed)
        start = self._ensure_public(image_url)
        if start:
            body["start_image"] = start
        end = self._ensure_public(end_image)
        if end:
            body["end_image"] = end  # end_image и reference_images взаимоисключающие (Seedance)
        elif reference_images:
            body["reference_images"] = [u for u in (self._ensure_public(u) for u in reference_images) if u][:9]
        if reference_audios:
            body["reference_audios"] = [u for u in (self._ensure_public(u) for u in reference_audios) if u][:3]
        return self.run(f"video/{model}", body)

    def text_to_video(self, prompt: str, **kw) -> GenResult:
        return self.image_to_video(None, prompt, **kw)

    def lipsync(self, image_url: str, audio_url: str, *, prompt: str = "", duration: float = 5,
                aspect_ratio: str = "16:9", resolution: str = "720p", model: str | None = None,
                **kwargs) -> GenResult:
        """Говорящий персонаж через Seedance: стартовый кадр + референс-аудио (@Audio1)."""
        p = (prompt.strip() + " " if prompt.strip() else "")
        p += ("@Image1 as the first frame. The character speaks on camera with lips synced precisely "
              "to @Audio1, natural facial expressions and subtle head movement, steady camera. "
              "Audio: use @Audio1 as the only voice, no music, no extra dialogue.")
        return self.image_to_video(image_url, p, reference_audios=[audio_url], duration=duration,
                                   aspect_ratio=aspect_ratio, resolution=resolution, model=model)

    # ---- звук ----
    def music(self, prompt: str, length_ms: int = 10000, instrumental: bool = True,
              model: str | None = None) -> GenResult:
        model = model or settings.krea_music_model
        body = {"prompt": prompt[:4000], "music_length_ms": int(_clamp(length_ms, 3000, 600000)),
                "force_instrumental": bool(instrumental)}
        return self.run(f"audio/{model}", body)

    def tts(self, text: str, voice_id: str | None = None, model_id: str = "eleven_multilingual_v2") -> GenResult:
        body: dict = {"prompt": text[:2000], "model_id": model_id}
        if voice_id:
            body["voice_id"] = voice_id
        return self.run("audio/elevenlabs/tts", body)


def estimate_cu(kind: str, *, seconds: float = 0, resolution: str = "720p", draft: bool = False) -> int:
    """Оценка списания compute units (для счётчика расходов)."""
    if kind == "image":
        return CU_IMAGE
    if kind == "video":
        per = CU_VIDEO_PER_SEC["draft"] if draft else CU_VIDEO_PER_SEC.get(resolution, 171)
        return int(per * max(4, seconds or 5))
    if kind == "music":
        return 40
    if kind == "voice":
        return 5
    return 0
