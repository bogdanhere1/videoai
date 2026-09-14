# Деплой на VPS (Beget)

Всё в Docker Compose, GPU не нужен (генерация по API).

## 1. Подготовка сервера
```bash
# Docker + compose plugin
curl -fsSL https://get.docker.com | sh

git clone https://github.com/bogdanhere1/videoai.git
cd videoai
cp .env.example .env
nano .env   # заполнить ключи (см. ниже)
```

## 2. Переменные `.env`
Обязательные:
- `POSTGRES_PASSWORD`, `S3_SECRET_KEY`, `SECRET_LINK_TOKEN` — задать свои значения
- `DATABASE_URL=postgresql+psycopg://studio:<POSTGRES_PASSWORD>@db:5432/videoai`
- `GEMINI_API_KEY` (формат `AQ.…`), `GEMINI_MODEL=gemini-3.1-flash-lite`
- `ELEVENLABS_API_KEY`
- `HIGGSFIELD_API_KEY=key:secret` (со страницы cloud.higgsfield.ai/api-keys)
- `VIDEO_PROVIDER=native`

> Для генерации Higgsfield нужен **пополненный API-баланс** на cloud.higgsfield.ai
> (отдельно от веб-подписки). Музыка ElevenLabs требует соответствующего тарифа.

## 3. Домен и доступ
В `Caddyfile` заменить `:80` на свой домен (авто-HTTPS). Включить логин/пароль:
```bash
docker run --rm caddy caddy hash-password --plaintext 'ПАРОЛЬ'
# вставить логин+хэш в блок basic_auth в Caddyfile
```
«Доступ по ссылке» = дать клиенту URL + один логин/пароль.

## 4. Запуск
```bash
docker compose up -d --build
docker compose logs -f api
```
- Студия: `https://<домен>/`
- API health: `https://<домен>/api/../health` (внутренне `/health`)
- Kitsu (ревью): порт `8081` (лучше отдельный поддомен)
- MinIO консоль: `9001`

## 5. Медиа-хранилище
Локально ассеты кладутся в `api/media` (том). На проде вынести на MinIO/S3
(`S3_*` уже в `.env`) — заменить `app/storage.py` на S3-загрузку. `/media`
должен быть публично доступен, т.к. Higgsfield скачивает по нему кадры
(альтернатива уже в коде — `upload_file` в Higgsfield перед video/lipsync).

## 6. Что зависит от внешних балансов
| Возможность | Условие |
|---|---|
| Сценарий, раскадровка, извлечение визуалов | Gemini — работает |
| Голос, SFX | ElevenLabs — работает |
| Музыка | тариф ElevenLabs с Music |
| Концепты, кадры, видео (DoP), липсинк | API-баланс Higgsfield |
| Финальная сборка | ffmpeg (есть в образе `api`) |
