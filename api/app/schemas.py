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


# ---- API request/response ----
class IdeaIn(BaseModel):
    text: str


class ScriptReviseIn(BaseModel):
    feedback: str


class ApprovalIn(BaseModel):
    note: str = ""
    actor: str = "owner"


class TranscriptOut(BaseModel):
    text: str
