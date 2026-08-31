"""FastAPI-оркестратор.

Фаза 0: health + модель данных.
Фаза 1: интейк идеи (текст/голос) + сценарий на Gemini с gate-подтверждениями.
Фаза 2: извлечение визуалов + генерация концептов (Higgsfield Soul) + гейты по ассетам.
"""
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from . import agent, storage
from .config import settings
from .db import Base, engine, get_db
from .models import Approval, Asset, AssetType, Project, Scene, Stage, Status
from .providers import get_video_provider
from .providers.elevenlabs import transcribe as stt_transcribe
from .schemas import ApprovalIn, IdeaIn, ScriptDraft, ScriptReviseIn, TranscriptOut

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
        text = stt_transcribe(audio, filename=file.filename or "audio.webm")
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


@app.post("/api/concepts/{asset_id}:generate")
def generate_concept(asset_id: str, db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if not asset or asset.type != AssetType.concept:
        raise HTTPException(404, "Концепт не найден")
    prompt = (asset.params_json or {}).get("prompt", "")
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
    db.commit()
    return _asset_dto(asset)


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
    return {
        "id": p.id, "title": p.title, "stage": p.stage, "status": p.status,
        "brief_text": p.brief_text, "logline": p.logline,
        "scenes": [
            {"id": s.id, "order": s.order, "script_text": s.script_text, "status": s.status}
            for s in sorted(p.scenes, key=lambda x: x.order)
        ],
        "concepts": [_asset_dto(a) for a in concepts],
    }
