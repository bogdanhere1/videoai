# AI Video Studio

Веб-студия производства AI-видеороликов с нодовым холстом и человеком-в-контуре
на каждом этапе: **идея → сценарий → визуал-стиль → раскадровка → шот-продакшн → сборка**.

Пользователь вводит идею (голос/текст), LLM-агент ведёт по стадиям и на каждой ждёт
подтверждения «ок / переделай». Высокий контроль над каждым элементом ролика:
камера, свет, голос, липсинк, музыка, SFX.

## Стек

| Слой | Технология |
|------|-----------|
| Фронтенд | React + React Flow (нодовый холст) + Vite |
| Оркестратор | FastAPI + Celery + Redis |
| БД | PostgreSQL |
| Хранилище ассетов | MinIO (S3-совместимое) |
| Сборка видео | ffmpeg |
| Ревью с клиентом | Kitsu (self-hosted, добавляется на Фазе 2) |
| Reverse-proxy / доступ | Caddy (secret link / basic-auth) |

## Внешние сервисы

- **Higgsfield API** — картинка (Soul), видео (i2v/t2v), камера, липсинк (Speak v2).
  Доступ через слой `api/app/providers/` — можно нативный Higgsfield или реселлер
  (Segmind / fal.ai / eachlabs) без изменения остального кода.
- **ElevenLabs** — голос (TTS), SFX, и STT (Scribe) для голосового ввода идеи.
- **Gemini** (Flash/Pro) — LLM-агент.

> GPU на сервере **не нужен** — вся генерация идёт по API.

## Фазы

- **0 — Фундамент** (текущая): модель данных + docker-скелет + проверка Higgsfield API.
- **1** — интейк (голос/текст) + сценарий с gate-подтверждениями.
- **2** — визуал-стиль (концепты) + подключение Kitsu.
- **3** — раскадровка.
- **4** — нодовый шот-эдитор (ядро): камера/свет/голос/липсинк/музыка/SFX.
- **5** — сборка (ffmpeg) + пост + финал-ревью.
- **6** — роли (ты/клиент), доступ, контроль расходов на API.

## Локальный запуск (когда будет Docker)

```bash
cp .env.example .env   # заполнить ключи
docker compose up -d
# api:   http://localhost:8000/health
# web:   http://localhost:5173
# minio: http://localhost:9001
```

## Локальный запуск без Docker (SQLite)

Для итерации на своей машине Postgres не обязателен — можно на SQLite.

**Бэкенд** (нужен Python 3.12):
```bash
cd api
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt
set DATABASE_URL=sqlite:///./dev.db
set GEMINI_API_KEY=AQ.твой-ключ
set ELEVENLABS_API_KEY=твой-ключ
uvicorn app.main:app --reload      # http://localhost:8000/health
```

**Фронтенд** (Node 22+):
```bash
cd web
npm install
npm run dev                         # http://localhost:5173  (проксирует /api → :8000)
```

Открыть `http://localhost:5173`, создать ролик → вписать/наговорить идею → сгенерировать
сценарий → согласовать сцены. GEMINI_MODEL по умолчанию `gemini-3.1-flash-lite`.
