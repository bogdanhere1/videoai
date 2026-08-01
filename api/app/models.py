"""Модель данных Фазы 0.

Иерархия: Project -> Scene -> Shot -> Asset(версии).
Плюс Character (консистентность персонажа), Approval (gate-подтверждения),
Job (асинхронные задачи генерации).

Принцип: ассеты не перезаписываются — каждая перегенерация = новая версия.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON, DateTime, Enum, Float, ForeignKey, Integer, String, Text, Boolean
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Stage(str, enum.Enum):
    idea = "idea"
    script = "script"
    style = "style"
    storyboard = "storyboard"
    shots = "shots"
    assembly = "assembly"


class Status(str, enum.Enum):
    draft = "draft"
    generating = "generating"
    review = "review"       # ждёт подтверждения человека
    approved = "approved"
    rejected = "rejected"   # «переделай»


class AssetType(str, enum.Enum):
    concept = "concept"
    frame = "frame"
    video = "video"
    voice = "voice"
    music = "music"
    sfx = "sfx"
    final = "final"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String, default="Untitled")
    owner: Mapped[str] = mapped_column(String, default="")
    brief_text: Mapped[str] = mapped_column(Text, default="")
    logline: Mapped[str] = mapped_column(Text, default="")
    stage: Mapped[Stage] = mapped_column(Enum(Stage), default=Stage.idea)
    status: Mapped[Status] = mapped_column(Enum(Status), default=Status.draft)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    scenes: Mapped[list["Scene"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    characters: Mapped[list["Character"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Character(Base):
    __tablename__ = "characters"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String)
    ref_asset_id: Mapped[str | None] = mapped_column(String, nullable=True)  # референс для консистентности
    style_notes: Mapped[str] = mapped_column(Text, default="")

    project: Mapped[Project] = relationship(back_populates="characters")


class Scene(Base):
    __tablename__ = "scenes"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    order: Mapped[int] = mapped_column(Integer, default=0)
    script_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[Status] = mapped_column(Enum(Status), default=Status.draft)

    project: Mapped[Project] = relationship(back_populates="scenes")
    shots: Mapped[list["Shot"]] = relationship(back_populates="scene", cascade="all, delete-orphan")


class Shot(Base):
    __tablename__ = "shots"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    scene_id: Mapped[str] = mapped_column(ForeignKey("scenes.id"))
    order: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(Text, default="")
    duration: Mapped[float] = mapped_column(Float, default=5.0)
    camera_json: Mapped[dict] = mapped_column(JSON, default=dict)     # пресет камеры + сила движения
    lighting_prompt: Mapped[str] = mapped_column(Text, default="")     # свет (промпт/референс)
    graph_json: Mapped[dict] = mapped_column(JSON, default=dict)       # состояние нодового шот-графа
    status: Mapped[Status] = mapped_column(Enum(Status), default=Status.draft)

    scene: Mapped[Scene] = relationship(back_populates="shots")
    assets: Mapped[list["Asset"]] = relationship(back_populates="shot", cascade="all, delete-orphan")


class Asset(Base):
    __tablename__ = "assets"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    shot_id: Mapped[str | None] = mapped_column(ForeignKey("shots.id"), nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    type: Mapped[AssetType] = mapped_column(Enum(AssetType))
    url: Mapped[str] = mapped_column(String, default="")               # ключ в MinIO
    version: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String, default="")            # higgsfield|elevenlabs|upload
    job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    params_json: Mapped[dict] = mapped_column(JSON, default=dict)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    shot: Mapped[Shot | None] = relationship(back_populates="assets")


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    target_type: Mapped[str] = mapped_column(String)   # project|scene|shot|asset
    target_id: Mapped[str] = mapped_column(String)
    decision: Mapped[str] = mapped_column(String)      # approved|rejected
    note: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String, default="")
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String)          # higgsfield|elevenlabs|...
    external_job_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus), default=JobStatus.queued)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
