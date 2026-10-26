"""Krea public API (https://api.krea.ai) — универсальный провайдер: картинка, видео, музыка, TTS.

Подтверждено живым вызовом (26.10.2026):
  POST /generate/{category}/{vendor}/{model}  body = поля схемы модели  → {"job_id", "status"}
  GET  /jobs/{job_id} → {"status": ..., "result": {"urls": [...]}}; failed → result.error
  POST /assets  multipart(file=…, description=…) → {"image_url": ...}  (локальные файлы → публичный URL)
Auth: Authorization: Bearer <token> (krea.ai/settings/api-tokens).
БИЛЛИНГ: HTTP-токен списывает с ОТДЕЛЬНОГО API-баланса (пополнение от $5 на krea.ai/app/api),
а не с compute units веб-плана. 402 = баланс пуст.
Каждая модель принимает только свои поля (additionalProperties=false) → см. MODEL_FIELDS.

Режим KREA_MODE=agent: генерация через Krea Agent API (POST /agent/send-message → POST /agent/wait-for-session
→ media[].jobId → GET /jobs/{id}). По докам агент списывает compute units ПЛАНА даже с API-ключом,
поэтому API-баланс пополнять не нужно. Минус: модель/параметры задаются инструкцией в промпте, медленнее.
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
    "google/nano-banana-flash-lite": {"aspect_ratio", "image_urls"},  # без resolution (422 при передаче)
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
        self.mode = (settings.krea_mode or "direct").lower()

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

    # ---- Agent API (compute units плана) ----
    def agent_run(self, prompt: str, attachments: list[str] | None = None, *, name: str = "AI Video Studio",
                  timeout: float = 1200) -> dict:
        body: dict = {"prompt": prompt, "name": name[:120], "effort": "fast"}
        if attachments:
            body["attachments"] = [{"url": u} for u in attachments[:20]]
        r = httpx.post(f"{self.base_url}/agent/send-message", headers=self._headers(), json=body, timeout=60)
        if r.status_code == 402:
            raise KreaError(f"Krea Agent: закончились compute units плана ({r.text[:120]})")
        if r.status_code >= 400:
            raise KreaError(f"Krea Agent {r.status_code}: {r.text[:300]}")
        j = r.json()
        sid, rid = j.get("sessionId"), j.get("runId")
        t0 = time.time()
        while True:
            w = httpx.post(f"{self.base_url}/agent/wait-for-session", headers=self._headers(),
                           json={"sessionId": sid, "runId": rid, "timeoutSeconds": 120}, timeout=150)
            if w.status_code >= 400:
                raise KreaError(f"Krea Agent wait {w.status_code}: {w.text[:200]}")
            view = w.json()
            if view.get("finished"):
                if view.get("status") in ("failed", "cancelled"):
                    raise KreaError(f"Krea Agent {view.get('status')}: {view.get('error') or view.get('text', '')[:200]}")
                return view
            if time.time() - t0 > timeout:
                raise KreaError("Krea Agent: сессия не завершилась вовремя")

    def _agent_url(self, view: dict, kind: str) -> str | None:
        """Первый результат нужного типа из media[] сессии агента."""
        fallback = None
        for m in view.get("media") or []:
            if m.get("jobId"):
                mk = m.get("mediaKind")
                if mk and mk != kind:
                    continue
                urls = (self.job(m["jobId"]).get("result") or {}).get("urls") or []
                if urls:
                    return urls[0]
            elif m.get("url") and not fallback:
                fallback = m["url"]
        return fallback

    def _agent_generate(self, kind: str, instruction: str, attachments: list[str] | None = None) -> GenResult:
        rules = ("Run exactly ONE generation job with batch size 1 (a single output file) and stop immediately. "
                 "Do not create a second version, do not upscale, do not make variations, do not add extra steps, "
                 "do not ask questions. Use exactly the model and parameters specified. ")
        view = self.agent_run(rules + instruction, attachments)
        return GenResult(url=self._agent_url(view, kind), raw=view)

    # ---- картинка ----
    def generate_image(self, prompt: str, *, soul_id: str | None = None, seed: int | None = None,
                       model: str | None = None, aspect_ratio: str = "16:9", resolution: str = "1K",
                       image_urls: list[str] | None = None, **kwargs) -> GenResult:
        model = model or self.image_model
        if self.mode == "agent":
            refs = [u for u in (self._ensure_public(u) for u in (image_urls or [])) if u][:4]
            instr = (f"Generate ONE image with model {model}, aspect ratio {aspect_ratio}, resolution {resolution}. "
                     + ("Use the attached images as style/character references. " if refs else "")
                     + f"Image prompt: {prompt}")
            return self._agent_generate("image", instr, refs)
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
        start = self._ensure_public(image_url)
        if self.mode == "agent":
            lim = VIDEO_LIMITS.get(model, {"max": 15, "res": ("480p", "720p")})
            dur = int(_clamp(round(duration or 5), 4, lim["max"]))
            res_txt = "draft (fast 480p preview)" if draft else resolution
            att, roles = [], []
            if start:
                att.append(start); roles.append(f"attachment {len(att)} is the FIRST frame")
            end = self._ensure_public(end_image)
            if end:
                att.append(end); roles.append(f"attachment {len(att)} is the LAST frame")
            elif reference_images:
                for u in (self._ensure_public(u) for u in reference_images[:6]):
                    if u:
                        att.append(u); roles.append(f"attachment {len(att)} is a character/scene reference")
            for u in (self._ensure_public(u) for u in (reference_audios or [])[:2]):
                if u:
                    att.append(u); roles.append(f"attachment {len(att)} is the voice audio to lip-sync")
            instr = (f"Generate ONE video with model {model}: duration {dur} seconds, aspect ratio {aspect_ratio}, "
                     f"quality {res_txt}. " + ("; ".join(roles) + ". " if roles else "") + f"Video prompt: {prompt}")
            return self._agent_generate("video", instr, att)
        body = self._video_body(model, prompt, duration=duration, aspect_ratio=aspect_ratio,
                                resolution=resolution, draft=draft, seed=seed)
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
        if self.mode == "agent":
            secs = int(_clamp(length_ms, 3000, 600000) / 1000)
            instr = (f"Generate ONE {'instrumental ' if instrumental else ''}music track with model {model}, "
                     f"length {secs} seconds. Music prompt: {prompt[:3000]}")
            return self._agent_generate("audio", instr)
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
