"""FastAPI-оркестратор.

Фаза 0: health + модель данных.
Фаза 1: интейк идеи (текст/голос) + сценарий на Gemini с gate-подтверждениями.
Фаза 2: извлечение визуалов + генерация концептов (Higgsfield Soul) + гейты по ассетам.
"""
import hashlib
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import agent, assembly, storage
from .config import settings
from .db import Base, engine, get_db
from .models import (
    Approval, Asset, AssetType, Job, JobStatus, Modifier, Project, Scene, Shot, Stage,
    StageSetting, Status,
)
from .presets import CAMERA_PRESETS
from .providers import elevenlabs as el
from .providers import get_video_provider
from .schemas import (
    ApprovalIn, ConceptEdit, IdeaIn, ModifierIn, ModifierPatch, SceneEdit, ScriptDraft,
    ScriptReviseIn, ShotPatch, StageSettingIn, TranscriptOut,
)

STAGE_KEYS = ["idea", "script", "style", "storyboard", "shots", "assembly"]

os.makedirs(settings.media_dir, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)  # Alembic — позже
    yield


app = FastAPI(title="AI Video Studio API", lifespan=lifespan)
app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")


@app.get("/health")
def health():
    return {"status": "ok", "env": settings.app_env, "video_provider": settings.video_provider}


# ---------- Проекты ----------
@app.post("/api/projects")
def create_project(title: str = "Untitled", db: Session = Depends(get_db)):
    project = Project(title=title, stage=Stage.idea, status=Status.draft)
    db.add(project)
    db.commit()
    db.refresh(project)
    return _project_dto(project, db)


@app.get("/api/projects")
def list_projects(db: Session = Depends(get_db)):
    rows = db.query(Project).order_by(Project.created_at.desc()).all()
    return [{"id": p.id, "title": p.title, "stage": p.stage, "status": p.status} for p in rows]


@app.get("/api/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)):
    return _project_dto(_get_project(db, project_id), db)


# ---------- Стадия 1: идея ----------
@app.post("/api/projects/{project_id}/idea")
def set_idea(project_id: str, body: IdeaIn, db: Session = Depends(get_db)):
    project = _get_project(db, project_id)
    project.brief_text = body.text.strip()
    project.stage = Stage.idea
    project.status = Status.approved
    db.commit()
    return _project_dto(project, db)


@app.post("/api/transcribe", response_model=TranscriptOut)
async def transcribe(file: UploadFile = File(...)):
    audio = await file.read()
    try:
        text = el.transcribe(audio, filename=file.filename or "audio.webm")
    except Exception as e:
        raise HTTPException(502, f"STT error: {e}")
    return TranscriptOut(text=text)


# ---------- Стадия 2: сценарий ----------
@app.post("/api/projects/{project_id}/script:generate")
def generate_script(project_id: str, db: Session = Depends(get_db)):
    project = _get_project(db, project_id)
    if not project.brief_text:
        raise HTTPException(400, "Сначала задай идею (brief).")
    try:
        draft = agent.generate_script(project.brief_text)
    except Exception as e:
        raise HTTPException(502, f"Gemini error: {e}")
    _apply_draft(db, project, draft)
    return _project_dto(project, db)


@app.post("/api/projects/{project_id}/script:revise")
def revise_script(project_id: str, body: ScriptReviseIn, db: Session = Depends(get_db)):
    project = _get_project(db, project_id)
    previous = _draft_from_db(project)
    try:
        draft = agent.revise_script(project.brief_text, previous, body.feedback)
    except Exception as e:
        raise HTTPException(502, f"Gemini error: {e}")
    _apply_draft(db, project, draft)
    return _project_dto(project, db)


@app.patch("/api/scenes/{scene_id}")
def edit_scene(scene_id: str, body: SceneEdit, db: Session = Depends(get_db)):
    """Ручная правка текста сцены (поправить слово, не перегенерируя)."""
    scene = db.get(Scene, scene_id)
    if not scene:
        raise HTTPException(404, "Сцена не найдена")
    scene.script_text = body.script_text
    db.commit()
    return _project_dto(db.get(Project, scene.project_id), db)


# ---------- Стадия 3: визуал-стиль ----------
@app.post("/api/projects/{project_id}/visuals:extract")
def extract_visuals(project_id: str, db: Session = Depends(get_db)):
    project = _get_project(db, project_id)
    script_text = "\n\n".join(s.script_text for s in sorted(project.scenes, key=lambda x: x.order))
    if not script_text:
        raise HTTPException(400, "Сначала сгенерируй сценарий.")
    try:
        visuals = agent.extract_visuals(project.brief_text, script_text)
    except Exception as e:
        raise HTTPException(502, f"Gemini error: {e}")
    # Заменяем прежние концепт-ассеты проекта
    db.query(Asset).filter(
        Asset.project_id == project_id, Asset.type == AssetType.concept
    ).delete()
    for it in visuals.items:
        db.add(Asset(
            project_id=project_id, type=AssetType.concept, url="",
            params_json={"kind": it.kind, "name": it.name, "prompt": it.prompt},
        ))
    project.stage = Stage.style
    project.status = Status.review
    db.commit()
    return _project_dto(project, db)


@app.patch("/api/concepts/{asset_id}")
def edit_concept(asset_id: str, body: ConceptEdit, db: Session = Depends(get_db)):
    """Ручная правка промпта концепта (перед генерацией)."""
    asset = db.get(Asset, asset_id)
    if not asset or asset.type != AssetType.concept:
        raise HTTPException(404, "Концепт не найден")
    p = dict(asset.params_json or {})
    p["prompt"] = body.prompt
    asset.params_json = p
    db.commit()
    return _asset_dto(asset)


@app.post("/api/concepts/{asset_id}:generate")
def generate_concept(asset_id: str, db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if not asset or asset.type != AssetType.concept:
        raise HTTPException(404, "Концепт не найден")
    prompt = _style_prefix(db, asset.project_id, "style") + (asset.params_json or {}).get("prompt", "")
    try:
        res = get_video_provider().generate_image(prompt)
    except Exception as e:
        raise HTTPException(502, f"Higgsfield error: {e}")
    if not res.url:
        raise HTTPException(502, "Провайдер не вернул URL картинки")
    try:
        stored = storage.save_from_url(res.url)
    except Exception as e:
        raise HTTPException(502, f"Не удалось скачать результат: {e}")
    asset.url = stored
    asset.version += 1
    asset.source = "higgsfield"
    asset.approved = False
    _log_usage(db, asset.project_id, "concept", "higgsfield", COST_USD["concept"])
    db.commit()
    return _asset_dto(asset)


# ---------- Стадия 4: раскадровка ----------
@app.post("/api/projects/{project_id}/storyboard:generate")
def generate_storyboard(project_id: str, db: Session = Depends(get_db)):
    project = _get_project(db, project_id)
    scenes = sorted(project.scenes, key=lambda x: x.order)
    if not scenes:
        raise HTTPException(400, "Сначала сгенерируй сценарий.")
    script_text = "\n\n".join(f"Сцена {s.order}: {s.script_text}" for s in scenes)
    concepts = db.query(Asset).filter(
        Asset.project_id == project_id, Asset.type == AssetType.concept
    ).all()
    visuals = "\n".join(
        f"- {(c.params_json or {}).get('kind')} «{(c.params_json or {}).get('name')}»: "
        f"{(c.params_json or {}).get('prompt', '')}" for c in concepts
    ) or "(визуалы ещё не заданы)"
    try:
        board = agent.breakdown_storyboard(project.brief_text, script_text, visuals)
    except Exception as e:
        raise HTTPException(502, f"Gemini error: {e}")
    by_order = {s.order: s for s in scenes}
    for s in scenes:
        db.query(Shot).filter(Shot.scene_id == s.id).delete()
    for sp in board.shots:
        scene = by_order.get(sp.scene_order, scenes[0])
        db.add(Shot(
            scene_id=scene.id, order=sp.order, description=sp.description,
            duration=sp.duration, lighting_prompt=sp.lighting,
            camera_json={"movement": sp.camera, "frame_prompt": sp.frame_prompt},
            status=Status.review,
        ))
    project.stage = Stage.storyboard
    project.status = Status.review
    db.commit()
    return _project_dto(project, db)


_FRAME_HINT = {
    "single": "",
    "start": ", first frame of the shot, starting pose and composition",
    "end": ", final frame of the SAME shot — keep the exact same character, wardrobe, "
           "location and lighting as the start frame, only the pose/action changes to the ending",
}


def _stable_seed(text: str) -> int:
    return int(hashlib.md5(text.encode()).hexdigest()[:6], 16) % 1_000_000


@app.post("/api/shots/{shot_id}:frame")
def generate_frame(shot_id: str, variant: str = "single", db: Session = Depends(get_db)):
    """Статичный кадр раскадровки. variant: single | start | end.
    start/end делаются с одним сидом на шот → консистентная сцена, меняется поза/действие."""
    shot = db.get(Shot, shot_id)
    if not shot:
        raise HTTPException(404, "Шот не найден")
    if variant not in _FRAME_HINT:
        raise HTTPException(400, "variant: single|start|end")
    base = (shot.camera_json or {}).get("frame_prompt") or shot.description
    prompt = _style_prefix(db, _shot_project_id(shot), "storyboard") + base + _FRAME_HINT[variant]
    seed = _stable_seed(shot_id)  # общий сид старта/финала одного шота → консистентность
    try:
        res = get_video_provider().generate_image(prompt, seed=seed)
    except Exception as e:
        raise HTTPException(502, f"Higgsfield error: {e}")
    if not res.url:
        raise HTTPException(502, "Провайдер не вернул URL кадра")
    try:
        stored = storage.save_from_url(res.url)
    except Exception as e:
        raise HTTPException(502, f"Не удалось скачать кадр: {e}")
    frames = db.query(Asset).filter(Asset.shot_id == shot_id, Asset.type == AssetType.frame).all()
    frame = next((a for a in frames if (a.params_json or {}).get("variant", "single") == variant), None)
    if frame:
        frame.url, frame.approved = stored, False
        frame.version += 1
    else:
        db.add(Asset(shot_id=shot_id, type=AssetType.frame, url=stored, source="higgsfield",
                     params_json={"variant": variant}))
    _log_usage(db, _shot_project_id(shot), "frame", "higgsfield", COST_USD["frame"])
    db.commit()
    return _shot_dto(db, shot)


# ---------- Стадия 5: шот-эдитор (элементы шота) ----------
@app.get("/api/voices")
def voices():
    try:
        return el.list_voices()
    except Exception as e:
        raise HTTPException(502, f"ElevenLabs error: {e}")


@app.get("/api/camera-presets")
def camera_presets():
    return CAMERA_PRESETS


@app.patch("/api/shots/{shot_id}")
def patch_shot(shot_id: str, body: ShotPatch, db: Session = Depends(get_db)):
    shot = db.get(Shot, shot_id)
    if not shot:
        raise HTTPException(404, "Шот не найден")
    g = dict(shot.graph_json or {})
    if body.description is not None:
        shot.description = body.description
    if body.lighting is not None:
        shot.lighting_prompt = body.lighting
    if body.frame_mode is not None:
        g["frame_mode"] = body.frame_mode
    for field in ("camera_preset", "motion_strength", "voice_text", "voice_id",
                  "music_prompt", "sfx_prompt"):
        val = getattr(body, field)
        if val is not None:
            g[field] = val
    shot.graph_json = g
    db.commit()
    return _shot_dto(db, shot)


@app.post("/api/shots/{shot_id}/voice:generate")
def gen_voice(shot_id: str, db: Session = Depends(get_db)):
    shot, g = _shot_and_graph(db, shot_id)
    text = g.get("voice_text", "").strip()
    if not text:
        raise HTTPException(400, "Пустой текст озвучки")
    voice_id = g.get("voice_id")
    if not voice_id:
        try:
            vs = el.list_voices()
            voice_id = vs[0]["voice_id"] if vs else "21m00Tcm4TlvDq8ikWAM"
        except Exception:
            voice_id = "21m00Tcm4TlvDq8ikWAM"
    try:
        audio = el.tts(text, voice_id)
    except Exception as e:
        raise HTTPException(502, f"ElevenLabs TTS error: {e}")
    _save_shot_asset(db, shot_id, AssetType.voice, storage.save_bytes(audio, ".mp3"), "elevenlabs")
    _log_usage(db, _shot_project_id(shot), "voice", "elevenlabs", COST_USD["voice"])
    db.commit()
    return _shot_dto(db, shot)


@app.post("/api/shots/{shot_id}/sfx:generate")
def gen_sfx(shot_id: str, db: Session = Depends(get_db)):
    shot, g = _shot_and_graph(db, shot_id)
    prompt = g.get("sfx_prompt", "").strip()
    if not prompt:
        raise HTTPException(400, "Пустой промпт SFX")
    try:
        audio = el.sound_effect(prompt, duration_seconds=min(shot.duration or 5, 22))
    except Exception as e:
        raise HTTPException(502, f"ElevenLabs SFX error: {e}")
    _save_shot_asset(db, shot_id, AssetType.sfx, storage.save_bytes(audio, ".mp3"), "elevenlabs")
    _log_usage(db, _shot_project_id(shot), "sfx", "elevenlabs", COST_USD["sfx"])
    db.commit()
    return _shot_dto(db, shot)


@app.post("/api/shots/{shot_id}/music:generate")
def gen_music(shot_id: str, db: Session = Depends(get_db)):
    shot, g = _shot_and_graph(db, shot_id)
    prompt = g.get("music_prompt", "").strip()
    if not prompt:
        raise HTTPException(400, "Пустой промпт музыки")
    try:
        audio = el.music(prompt, length_ms=int((shot.duration or 10) * 1000))
    except Exception as e:
        raise HTTPException(502, f"ElevenLabs music error: {e}")
    _save_shot_asset(db, shot_id, AssetType.music, storage.save_bytes(audio, ".mp3"), "elevenlabs")
    _log_usage(db, _shot_project_id(shot), "music", "elevenlabs", COST_USD["music"])
    db.commit()
    return _shot_dto(db, shot)


@app.post("/api/shots/{shot_id}/video:generate")
def gen_video(shot_id: str, db: Session = Depends(get_db)):
    shot, g = _shot_and_graph(db, shot_id)
    frame = _shot_asset(db, shot_id, AssetType.frame)
    if not frame or not frame.url:
        raise HTTPException(400, "Нет ключевого кадра — сначала сгенерируй кадр (Фаза 3)")
    frame_path = _media_fs_path(frame.url)
    camera = {"motion": g.get("camera_preset", "General"),
              "motion_strength": g.get("motion_strength", 0.6)}
    base = (shot.camera_json or {}).get("frame_prompt") or shot.description
    # модификаторы, подключённые к этапу «Шоты» (камера/свет/…), влияют на анимацию
    prompt = _style_prefix(db, _shot_project_id(shot), "shots") + base
    try:
        res = get_video_provider().image_to_video(frame_path, prompt, camera=camera)
    except Exception as e:
        raise HTTPException(502, f"Higgsfield DoP error: {e}")
    if not res.url:
        raise HTTPException(502, "Провайдер не вернул URL видео")
    _save_shot_asset(db, shot_id, AssetType.video, storage.save_from_url(res.url, ".mp4"), "higgsfield")
    _log_usage(db, _shot_project_id(shot), "video", "higgsfield",
               COST_USD["video_per_sec"] * (shot.duration or 5))
    db.commit()
    return _shot_dto(db, shot)


@app.post("/api/shots/{shot_id}/lipsync:generate")
def gen_lipsync(shot_id: str, db: Session = Depends(get_db)):
    shot, g = _shot_and_graph(db, shot_id)
    frame = _shot_asset(db, shot_id, AssetType.frame)
    voice = _shot_asset(db, shot_id, AssetType.voice)
    if not frame or not frame.url:
        raise HTTPException(400, "Нет кадра для липсинка")
    if not voice or not voice.url:
        raise HTTPException(400, "Нет озвучки — сначала сгенерируй голос")
    try:
        res = get_video_provider().lipsync(_media_fs_path(frame.url), _media_fs_path(voice.url))
    except Exception as e:
        raise HTTPException(502, f"Higgsfield Speak error: {e}")
    if not res.url:
        raise HTTPException(502, "Провайдер не вернул URL липсинка")
    _save_shot_asset(db, shot_id, AssetType.video, storage.save_from_url(res.url, ".mp4"), "higgsfield")
    _log_usage(db, _shot_project_id(shot), "lipsync", "higgsfield", COST_USD["lipsync"])
    db.commit()
    return _shot_dto(db, shot)


# ---------- Настройки: API-подключения по этапам ----------
@app.get("/api/projects/{project_id}/settings")
def get_settings(project_id: str, db: Session = Depends(get_db)):
    _get_project(db, project_id)
    rows = {s.stage: s for s in db.query(StageSetting).filter(StageSetting.project_id == project_id).all()}
    out = {}
    for stage in STAGE_KEYS:
        s = rows.get(stage)
        out[stage] = {
            "provider": s.provider if s else "",
            "api_key": s.api_key if s else "",
            "base_url": s.base_url if s else "",
            "model": s.model if s else "",
            "enabled": s.enabled if s else False,
        }
    return out


@app.put("/api/projects/{project_id}/settings/{stage}")
def put_setting(project_id: str, stage: str, body: StageSettingIn, db: Session = Depends(get_db)):
    _get_project(db, project_id)
    if stage not in STAGE_KEYS:
        raise HTTPException(400, "Неизвестный этап")
    row = db.query(StageSetting).filter(
        StageSetting.project_id == project_id, StageSetting.stage == stage
    ).first()
    if not row:
        row = StageSetting(project_id=project_id, stage=stage)
        db.add(row)
    row.provider, row.api_key = body.provider, body.api_key
    row.base_url, row.model, row.enabled = body.base_url, body.model, body.enabled
    db.commit()
    return {"stage": stage, "enabled": row.enabled, "provider": row.provider}


# ---------- Узлы-модификаторы (напр. «Стиль») ----------
def _modifier_dto(m: Modifier) -> dict:
    return {
        "id": m.id, "kind": m.kind, "target_stage": m.target_stage,
        "reference_text": m.reference_text, "refs": m.refs_json or [],
        "enabled": m.enabled, "pos_x": m.pos_x, "pos_y": m.pos_y,
    }


MOD_LABEL = {"style": "Style", "character": "Character", "camera": "Camera",
             "light": "Lighting", "location": "Location"}
ALL_MOD_KINDS = tuple(MOD_LABEL.keys())


def _mod_targets(m: Modifier) -> set:
    """Множество этапов, к которым подключён модификатор (мульти-цель)."""
    raw = (m.target_stage or "").strip()
    if not raw or raw == "none":
        return set()
    if raw == "both":          # legacy
        return {"style", "storyboard"}
    return {s for s in raw.split(",") if s}


def _style_prefix(db: Session, project_id: str, stage: str, kinds=ALL_MOD_KINDS) -> str:
    """Собирает текст из включённых узлов-модификаторов, подключённых к этапу."""
    mods = db.query(Modifier).filter(
        Modifier.project_id == project_id, Modifier.kind.in_(kinds),
        Modifier.enabled == True,  # noqa: E712
    ).all()
    parts = []
    for m in mods:
        t = (m.reference_text or "").strip()
        if not t or stage not in _mod_targets(m):
            continue
        parts.append(f"{MOD_LABEL.get(m.kind, 'Ref')}: {t}")
    return (" | ".join(parts) + ". ") if parts else ""


def _view_prompts(kind: str, desc: str, style: str) -> list[tuple[str, str]]:
    """Специализированные промпты «видов» для узлов-генераторов."""
    if kind == "character":
        return [
            ("Тело · фронт (без головы)",
             f"{style}full body character reference sheet of {desc}, cropped at the neck, "
             f"headless, no head visible, detailed outfit and footwear, standing neutral A-pose, "
             f"plain light-grey studio backdrop, sharp high detail, photoreal"),
            ("Тело · 3/4 (без головы)",
             f"{style}full body character reference of {desc}, three-quarter view, cropped at the "
             f"neck, headless, no head visible, detailed clothing, plain studio backdrop, high detail"),
            ("Лицо · крупный план",
             f"{style}extreme close-up beauty portrait, only the head and face of {desc}, highly "
             f"detailed facial features and skin texture, sharp focus, front view, soft studio "
             f"lighting, plain background"),
        ]
    if kind == "location":
        return [
            ("Общий план",
             f"{style}wide establishing shot of {desc}, no people, empty scene, cinematic, "
             f"detailed environment, natural lighting, high detail"),
            ("Другой ракурс",
             f"{style}{desc}, alternate wide angle, no people, detailed environment, depth"),
            ("Деталь · атмосфера",
             f"{style}atmospheric detail shot inside {desc}, close-up on textures and props, "
             f"no people, moody lighting, shallow depth of field"),
        ]
    return []


@app.get("/api/projects/{project_id}/modifiers")
def list_modifiers(project_id: str, db: Session = Depends(get_db)):
    _get_project(db, project_id)
    rows = db.query(Modifier).filter(Modifier.project_id == project_id).all()
    return [_modifier_dto(m) for m in rows]


@app.post("/api/projects/{project_id}/modifiers")
def create_modifier(project_id: str, body: ModifierIn, db: Session = Depends(get_db)):
    _get_project(db, project_id)
    n = db.query(Modifier).filter(Modifier.project_id == project_id).count()
    m = Modifier(project_id=project_id, kind=body.kind, target_stage=body.target_stage,
                 pos_x=120.0 + (n % 4) * 300.0, pos_y=360.0 + (n // 4) * 220.0)
    db.add(m)
    db.commit()
    db.refresh(m)
    return _modifier_dto(m)


@app.patch("/api/modifiers/{mid}")
def patch_modifier(mid: str, body: ModifierPatch, db: Session = Depends(get_db)):
    m = db.get(Modifier, mid)
    if not m:
        raise HTTPException(404, "Узел не найден")
    for field in ("reference_text", "target_stage", "enabled", "pos_x", "pos_y"):
        val = getattr(body, field)
        if val is not None:
            setattr(m, field, val)
    db.commit()
    return _modifier_dto(m)


@app.post("/api/modifiers/{mid}/reference")
async def upload_reference(mid: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    m = db.get(Modifier, mid)
    if not m:
        raise HTTPException(404, "Узел не найден")
    data = await file.read()
    ext = os.path.splitext(file.filename or "ref.png")[1] or ".png"
    url = storage.save_bytes(data, ext)
    m.refs_json = list(m.refs_json or []) + [url]
    db.commit()
    return _modifier_dto(m)


@app.post("/api/modifiers/{mid}/views:generate")
def generate_modifier_views(mid: str, db: Session = Depends(get_db)):
    """Генерит набор «видов» для узлов-генераторов (Персонаж/Локация)."""
    m = db.get(Modifier, mid)
    if not m:
        raise HTTPException(404, "Узел не найден")
    desc = (m.reference_text or "").strip()
    if not desc:
        raise HTTPException(400, "Заполни описание (референс-текст)")
    style = _style_prefix(db, m.project_id, "storyboard", kinds=("style", "camera", "light"))
    views = _view_prompts(m.kind, desc, style)
    if not views:
        raise HTTPException(400, "У этого узла нет генерации видов")
    provider = get_video_provider()
    out = list(m.refs_json or [])
    added, errors = 0, []
    for label, prompt in views:
        try:
            res = provider.generate_image(prompt)
            if res.url:
                out.append({"label": label, "url": storage.save_from_url(res.url)})
                _log_usage(db, m.project_id, "concept", "higgsfield", COST_USD["concept"])
                added += 1
        except Exception as e:
            errors.append(f"{label}: {e}")
    m.refs_json = out
    db.commit()
    if added == 0 and errors:
        raise HTTPException(502, "; ".join(errors)[:400])
    return _modifier_dto(m)


@app.delete("/api/modifiers/{mid}")
def delete_modifier(mid: str, db: Session = Depends(get_db)):
    m = db.get(Modifier, mid)
    if m:
        db.delete(m)
        db.commit()
    return {"ok": True}


# ---------- Стадия 6: сборка ----------
@app.post("/api/projects/{project_id}/assemble")
def assemble_project(project_id: str, db: Session = Depends(get_db)):
    project = _get_project(db, project_id)
    shots_data: list[dict] = []
    for scene in sorted(project.scenes, key=lambda x: x.order):
        for shot in sorted(scene.shots, key=lambda x: x.order):
            if shot.status == Status.rejected:
                continue
            assets = {a.type: a for a in db.query(Asset).filter(Asset.shot_id == shot.id).all()}
            audio = [assets[t].url for t in (AssetType.voice, AssetType.music, AssetType.sfx)
                     if t in assets and assets[t].url]
            shots_data.append({
                "video_url": assets[AssetType.video].url if AssetType.video in assets else "",
                "frame_url": assets[AssetType.frame].url if AssetType.frame in assets else "",
                "audio_urls": audio,
                "duration": shot.duration,
            })
    if not shots_data:
        raise HTTPException(400, "Нет шотов для сборки — сначала сделай раскадровку.")
    try:
        final_url = assembly.assemble(shots_data)
    except assembly.FFmpegMissing as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, f"Сборка не удалась: {e}")
    a = db.query(Asset).filter(Asset.project_id == project_id, Asset.type == AssetType.final).first()
    if a:
        a.url, a.version = final_url, a.version + 1
    else:
        db.add(Asset(project_id=project_id, type=AssetType.final, url=final_url, source="ffmpeg"))
    project.stage = Stage.assembly
    project.status = Status.review
    db.commit()
    return {"final_url": final_url, "shots": len(shots_data)}


# ---------- Gate-подтверждения ----------
@app.post("/api/scenes/{scene_id}/approve")
def approve_scene(scene_id: str, body: ApprovalIn, db: Session = Depends(get_db)):
    return _decide_scene(db, scene_id, Status.approved, body)


@app.post("/api/scenes/{scene_id}/reject")
def reject_scene(scene_id: str, body: ApprovalIn, db: Session = Depends(get_db)):
    return _decide_scene(db, scene_id, Status.rejected, body)


@app.post("/api/assets/{asset_id}/approve")
def approve_asset(asset_id: str, body: ApprovalIn, db: Session = Depends(get_db)):
    return _decide_asset(db, asset_id, True, body)


@app.post("/api/assets/{asset_id}/reject")
def reject_asset(asset_id: str, body: ApprovalIn, db: Session = Depends(get_db)):
    return _decide_asset(db, asset_id, False, body)


@app.post("/api/shots/{shot_id}/approve")
def approve_shot(shot_id: str, body: ApprovalIn, db: Session = Depends(get_db)):
    return _decide_shot(db, shot_id, Status.approved, body)


@app.post("/api/shots/{shot_id}/reject")
def reject_shot(shot_id: str, body: ApprovalIn, db: Session = Depends(get_db)):
    return _decide_shot(db, shot_id, Status.rejected, body)


# ---------- helpers ----------
def _get_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Проект не найден")
    return project


def _apply_draft(db: Session, project: Project, draft: ScriptDraft) -> None:
    project.logline = draft.logline
    project.stage = Stage.script
    project.status = Status.review
    db.query(Scene).filter(Scene.project_id == project.id).delete()
    for s in sorted(draft.scenes, key=lambda x: x.order):
        beats = "\n".join(f"• {b}" for b in s.beats)
        text = f"{s.title}\n{s.script_text}" + (f"\n{beats}" if beats else "")
        db.add(Scene(project_id=project.id, order=s.order, script_text=text, status=Status.review))
    db.commit()


def _draft_from_db(project: Project) -> ScriptDraft:
    from .schemas import ScriptScene
    scenes = []
    for sc in sorted(project.scenes, key=lambda x: x.order):
        lines = sc.script_text.split("\n")
        scenes.append(ScriptScene(
            order=sc.order,
            title=lines[0] if lines else "",
            script_text="\n".join(lines[1:]) if len(lines) > 1 else "",
            beats=[],
        ))
    return ScriptDraft(logline=project.logline, scenes=scenes)


def _decide_scene(db: Session, scene_id: str, decision: Status, body: ApprovalIn):
    scene = db.get(Scene, scene_id)
    if not scene:
        raise HTTPException(404, "Сцена не найдена")
    scene.status = decision
    db.add(Approval(target_type="scene", target_id=scene_id,
                    decision=decision.value, note=body.note, actor=body.actor))
    db.commit()
    return {"id": scene.id, "status": scene.status}


def _decide_asset(db: Session, asset_id: str, approved: bool, body: ApprovalIn):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(404, "Ассет не найден")
    asset.approved = approved
    db.add(Approval(target_type="asset", target_id=asset_id,
                    decision="approved" if approved else "rejected", note=body.note, actor=body.actor))
    db.commit()
    return _asset_dto(asset)


def _decide_shot(db: Session, shot_id: str, decision: Status, body: ApprovalIn):
    shot = db.get(Shot, shot_id)
    if not shot:
        raise HTTPException(404, "Шот не найден")
    shot.status = decision
    db.add(Approval(target_type="shot", target_id=shot_id,
                    decision=decision.value, note=body.note, actor=body.actor))
    db.commit()
    return _shot_dto(db, shot)


def _shot_and_graph(db: Session, shot_id: str) -> tuple[Shot, dict]:
    shot = db.get(Shot, shot_id)
    if not shot:
        raise HTTPException(404, "Шот не найден")
    return shot, dict(shot.graph_json or {})


def _shot_asset(db: Session, shot_id: str, atype: AssetType) -> Asset | None:
    return db.query(Asset).filter(Asset.shot_id == shot_id, Asset.type == atype).first()


def _save_shot_asset(db: Session, shot_id: str, atype: AssetType, url: str, source: str) -> None:
    a = _shot_asset(db, shot_id, atype)
    if a:
        a.url, a.source, a.approved = url, source, False
        a.version += 1
    else:
        db.add(Asset(shot_id=shot_id, type=atype, url=url, source=source))


def _media_fs_path(url: str) -> str:
    """/media/<name> → локальный путь файла (для загрузки в Higgsfield)."""
    name = url.rsplit("/", 1)[-1]
    return os.path.join(settings.media_dir, name)


# Ориентировочная стоимость генераций (USD) — для счётчика расходов.
COST_USD = {"concept": 0.05, "frame": 0.05, "voice": 0.01, "sfx": 0.01,
            "music": 0.02, "video_per_sec": 0.10, "lipsync": 0.10}


def _log_usage(db: Session, project_id: str | None, kind: str, provider: str, cost: float) -> None:
    db.add(Job(provider=provider, status=JobStatus.done,
               payload={"project_id": project_id, "kind": kind, "cost": round(cost, 4)}))


def _project_cost(db: Session, project_id: str) -> float:
    total = 0.0
    for j in db.query(Job).filter(Job.status == JobStatus.done).all():
        p = j.payload or {}
        if p.get("project_id") == project_id:
            total += float(p.get("cost", 0) or 0)
    return round(total, 2)


def _shot_project_id(shot: Shot) -> str | None:
    return shot.scene.project_id if shot.scene else None


def _shot_dto(db: Session, s: Shot) -> dict:
    g = s.graph_json or {}
    cam = s.camera_json or {}
    all_assets = db.query(Asset).filter(Asset.shot_id == s.id).all()
    frames = {(a.params_json or {}).get("variant", "single"): a.url
              for a in all_assets if a.type == AssetType.frame}
    other = {a.type: a for a in all_assets if a.type != AssetType.frame}
    return {
        "id": s.id, "order": s.order, "description": s.description,
        "camera": cam.get("movement", ""), "lighting": s.lighting_prompt,
        "duration": s.duration, "status": s.status,
        "frame_mode": g.get("frame_mode", "single"),
        "frame_single": frames.get("single", ""),
        "frame_start": frames.get("start", ""),
        "frame_end": frames.get("end", ""),
        "frame_url": frames.get("single") or frames.get("start") or "",
        "video_url": other[AssetType.video].url if AssetType.video in other else "",
        "voice_url": other[AssetType.voice].url if AssetType.voice in other else "",
        "music_url": other[AssetType.music].url if AssetType.music in other else "",
        "sfx_url": other[AssetType.sfx].url if AssetType.sfx in other else "",
        "camera_preset": g.get("camera_preset", "General"),
        "motion_strength": g.get("motion_strength", 0.6),
        "voice_text": g.get("voice_text", ""),
        "voice_id": g.get("voice_id", ""),
        "music_prompt": g.get("music_prompt", ""),
        "sfx_prompt": g.get("sfx_prompt", ""),
    }


def _asset_dto(a: Asset) -> dict:
    p = a.params_json or {}
    return {
        "id": a.id, "kind": p.get("kind"), "name": p.get("name"), "prompt": p.get("prompt"),
        "url": a.url, "version": a.version, "approved": a.approved, "type": a.type,
    }


def _project_dto(p: Project, db: Session) -> dict:
    concepts = db.query(Asset).filter(
        Asset.project_id == p.id, Asset.type == AssetType.concept
    ).all()
    final = db.query(Asset).filter(
        Asset.project_id == p.id, Asset.type == AssetType.final
    ).first()
    return {
        "id": p.id, "title": p.title, "stage": p.stage, "status": p.status,
        "final_url": final.url if final else "",
        "cost_usd": _project_cost(db, p.id),
        "brief_text": p.brief_text, "logline": p.logline,
        "scenes": [
            {
                "id": s.id, "order": s.order, "script_text": s.script_text, "status": s.status,
                "shots": [_shot_dto(db, sh) for sh in sorted(s.shots, key=lambda x: x.order)],
            }
            for s in sorted(p.scenes, key=lambda x: x.order)
        ],
        "concepts": [_asset_dto(a) for a in concepts],
    }
