"""LLM-агент на Gemini.

Фаза 1: превращает идею в структурированный сценарий (сцены + биты) и
перерабатывает его по фидбеку пользователя. Структурированный вывод —
через response_schema (pydantic), поэтому парсинг надёжный.
"""
from google import genai
from google.genai import types

from .config import settings
from .schemas import ScriptDraft, VisualList

_SYSTEM = (
    "Ты — сценарист AI-видеостудии. По идее пользователя строишь чёткий, "
    "снимаемый сценарий короткого ролика: логлайн + последовательность сцен, "
    "в каждой сцене действие, место, настроение и ключевые биты. "
    "Пиши на языке идеи пользователя. Сцен обычно 3-8, ролик короткий. "
    "Не добавляй пояснений вне структуры."
)


def _client() -> genai.Client:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY не задан в .env")
    return genai.Client(api_key=settings.gemini_api_key)


def _generate(prompt: str) -> ScriptDraft:
    client = _client()
    resp = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM,
            response_mime_type="application/json",
            response_schema=ScriptDraft,
            temperature=0.8,
        ),
    )
    # У google-genai 1.47 есть .parsed для распарсенного pydantic-объекта.
    parsed = getattr(resp, "parsed", None)
    if isinstance(parsed, ScriptDraft):
        return parsed
    return ScriptDraft.model_validate_json(resp.text)


def generate_script(brief: str) -> ScriptDraft:
    return _generate(f"Идея ролика:\n{brief}\n\nСоставь сценарий.")


_ART_SYSTEM = (
    "Ты — арт-директор AI-видеостудии. По сценарию выделяешь визуальные сущности: "
    "персонажей (character) и локации/окружения (environment). Для каждой даёшь "
    "детальный промпт для генератора изображений НА АНГЛИЙСКОМ (стиль, свет, композиция, "
    "материалы, настроение), а поле name — на языке сценария. Не выдумывай лишних сущностей."
)


def extract_visuals(brief: str, script_text: str) -> VisualList:
    client = _client()
    resp = client.models.generate_content(
        model=settings.gemini_model,
        contents=f"Идея:\n{brief}\n\nСценарий:\n{script_text}\n\nВыдели персонажей и окружения.",
        config=types.GenerateContentConfig(
            system_instruction=_ART_SYSTEM,
            response_mime_type="application/json",
            response_schema=VisualList,
            temperature=0.7,
        ),
    )
    parsed = getattr(resp, "parsed", None)
    if isinstance(parsed, VisualList):
        return parsed
    return VisualList.model_validate_json(resp.text)


def revise_script(brief: str, previous: ScriptDraft, feedback: str) -> ScriptDraft:
    prompt = (
        f"Идея ролика:\n{brief}\n\n"
        f"Текущий сценарий (JSON):\n{previous.model_dump_json(indent=2)}\n\n"
        f"Правки от пользователя:\n{feedback}\n\n"
        "Переделай сценарий с учётом правок, сохранив удачное."
    )
    return _generate(prompt)
