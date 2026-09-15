"""Pydantic-схемы запросов/ответов и структурированного вывода Gemini."""
from pydantic import BaseModel, Field


# ---- Структурированный вывод сценария (response_schema для Gemini) ----
class ScriptScene(BaseModel):
    order: int = Field(description="Порядковый номер сцены, с 1")
    title: str = Field(description="Короткое название сцены")
    script_text: str = Field(description="Что происходит в сцене: действие, место, настроение")
    beats: list[str] = Field(description="2-5 ключевых битов сцены")


class ScriptDraft(BaseModel):
    logline: str = Field(description="Одна фраза — суть ролика")
    scenes: list[ScriptScene]


# ---- Извлечение визуалов (Фаза 2) ----
class VisualSpec(BaseModel):
    kind: str = Field(description='"character" или "environment"')
    name: str = Field(description="Имя/название на языке сценария (для UI)")
    prompt: str = Field(description="Детальный промпт для генерации концепта на английском (для Soul)")


class VisualList(BaseModel):
    items: list[VisualSpec]


# ---- Раскадровка (Фаза 3) ----
class ShotSpec(BaseModel):
    scene_order: int = Field(description="Номер сцены, к которой относится шот")
    order: int = Field(description="Порядок шота внутри сцены, с 1")
    description: str = Field(description="Что в кадре: действие, кто, ракурс — на языке сценария")
    camera: str = Field(description="Движение/раскадровка камеры, напр. 'slow dolly in', 'handheld'")
    lighting: str = Field(description="Свет: источник и настроение")
    duration: float = Field(description="Длительность шота в секундах, 2–8")
    frame_prompt: str = Field(description="Детальный промпт ключевого кадра НА АНГЛИЙСКОМ (для Soul)")


class Storyboard(BaseModel):
    shots: list[ShotSpec]


class ConceptEdit(BaseModel):
    prompt: str


# ---- Шот-эдитор (Фаза 4) ----
class ShotPatch(BaseModel):
    description: str | None = None
    lighting: str | None = None
    camera_preset: str | None = None
    motion_strength: float | None = None
    voice_text: str | None = None
    voice_id: str | None = None
    music_prompt: str | None = None
    sfx_prompt: str | None = None


# ---- API request/response ----
class IdeaIn(BaseModel):
    text: str


class ScriptReviseIn(BaseModel):
    feedback: str


class SceneEdit(BaseModel):
    script_text: str


class ApprovalIn(BaseModel):
    note: str = ""
    actor: str = "owner"


class TranscriptOut(BaseModel):
    text: str
