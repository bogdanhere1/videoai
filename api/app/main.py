"""FastAPI-оркестратор.

Фаза 0: health + модель данных.
Фаза 1: интейк идеи (текст/голос) + сценарий на Gemini с gate-подтверждениями.
"""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from . import agent
from .config import settings
from .db import Base, engine, get_db
from .models import Approval, Project, Scene, Stage, Status
from .providers import elevenlabs
from .schemas import ApprovalIn, IdeaIn, ScriptDraft, ScriptReviseIn, TranscriptOut


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)  # Фаза 1: create_all; Alembic — позже
    yield


app = FastAPI(title="AI Video Studio API", lifespan=lifespan)


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
    return _project_dto(project)


@app.get("/api/projects")
def list_projects(db: Session = Depends(get_db)):
    rows = db.query(Project).order_by(Project.created_at.desc()).all()
    return [{"id": p.id, "title": p.title, "stage": p.stage, "status": p.status} for p in rows]


@app.get("/api/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)):
    return _project_dto(_get_project(db, project_id))


# ---------- Стадия 1: идея ----------
@app.post("/api/projects/{project_id}/idea")
def set_idea(project_id: str, body: IdeaIn, db: Session = Depends(get_db)):
    project = _get_project(db, project_id)
    project.brief_text = body.text.strip()
    project.stage = Stage.idea
    project.status = Status.approved
    db.commit()
    return _project_dto(project)


@app.post("/api/transcribe", response_model=TranscriptOut)
async def transcribe(file: UploadFile = File(...)):
    """Голос → текст (ElevenLabs Scribe) для голосового ввода идеи."""
    audio = await file.read()
    try:
        text = elevenlabs.transcribe(audio, filename=file.filename or "audio.webm")
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
    return _project_dto(project)


@app.post("/api/projects/{project_id}/script:revise")
def revise_script(project_id: str, body: ScriptReviseIn, db: Session = Depends(get_db)):
    project = _get_project(db, project_id)
    previous = _draft_from_db(project)
    try:
        draft = agent.revise_script(project.brief_text, previous, body.feedback)
    except Exception as e:
        raise HTTPException(502, f"Gemini error: {e}")
    _apply_draft(db, project, draft)
    return _project_dto(project)


# ---------- Gate-подтверждения ----------
@app.post("/api/scenes/{scene_id}/approve")
def approve_scene(scene_id: str, body: ApprovalIn, db: Session = Depends(get_db)):
    return _decide_scene(db, scene_id, Status.approved, body)


@app.post("/api/scenes/{scene_id}/reject")
def reject_scene(scene_id: str, body: ApprovalIn, db: Session = Depends(get_db)):
    return _decide_scene(db, scene_id, Status.rejected, body)


# ---------- helpers ----------
def _get_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Проект не найден")
    return project


def _apply_draft(db: Session, project: Project, draft: ScriptDraft) -> None:
    """Заменяем сцены новой версией сценария, ставим на ревью."""
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
    db.add(Approval(
        target_type="scene", target_id=scene_id,
        decision=decision.value, note=body.note, actor=body.actor,
    ))
    db.commit()
    return {"id": scene.id, "status": scene.status}


def _project_dto(p: Project) -> dict:
    return {
        "id": p.id,
        "title": p.title,
        "stage": p.stage,
        "status": p.status,
        "brief_text": p.brief_text,
        "logline": p.logline,
        "scenes": [
            {"id": s.id, "order": s.order, "script_text": s.script_text, "status": s.status}
            for s in sorted(p.scenes, key=lambda x: x.order)
        ],
    }
