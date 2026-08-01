"""FastAPI-оркестратор. Фаза 0: health + создание таблиц + базовые CRUD-заглушки."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session

from .config import settings
from .db import Base, engine, get_db
from .models import Project, Stage, Status


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Фаза 0: создаём схему напрямую. На Фазе 1 заменим на Alembic-миграции.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="AI Video Studio API", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "env": settings.app_env,
        "video_provider": settings.video_provider,
    }


@app.post("/api/projects")
def create_project(title: str = "Untitled", db: Session = Depends(get_db)):
    project = Project(title=title, stage=Stage.idea, status=Status.draft)
    db.add(project)
    db.commit()
    db.refresh(project)
    return {"id": project.id, "title": project.title, "stage": project.stage}


@app.get("/api/projects")
def list_projects(db: Session = Depends(get_db)):
    rows = db.query(Project).order_by(Project.created_at.desc()).all()
    return [{"id": p.id, "title": p.title, "stage": p.stage, "status": p.status} for p in rows]
