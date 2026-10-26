from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    secret_link_token: str = "change-me"

    database_url: str = "postgresql+psycopg://studio:change-me@db:5432/videoai"
    redis_url: str = "redis://redis:6379/0"

    s3_endpoint: str = "http://minio:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "change-me"
    s3_bucket: str = "assets"

    gemini_api_key: str = ""
    # Новые ключи (AQ.…) не видят gemini-2.5-*; рабочий дефолт — flash-lite.
    gemini_model: str = "gemini-3.1-flash-lite"

    # auto (krea если есть ключ, иначе higgsfield) | krea | native/higgsfield
    video_provider: str = "auto"
    # Формат ключа higgsfield-client: "key:secret" (заголовок Authorization: Key ...)
    higgsfield_api_key: str = ""
    higgsfield_base_url: str = "https://platform.higgsfield.ai"
    # application = путь эндпоинта модели
    soul_application: str = "/v1/text2image/soul"
    dop_application: str = "/v1/image2video/dop"
    speak_application: str = "/v1/speak/speak"

    elevenlabs_api_key: str = ""

    # Krea public API (api.krea.ai): картинки, видео, музыка. Токен — krea.ai/settings/api-tokens.
    # Биллинг: ОТДЕЛЬНЫЙ API-баланс (krea.ai/app/api), не compute units веб-плана.
    krea_api_key: str = ""
    krea_base_url: str = "https://api.krea.ai"
    krea_image_model: str = "google/nano-banana-2.1"
    krea_video_model: str = "bytedance/seedance-2-5"
    krea_music_model: str = "elevenlabs/music-v2.5"

    # Локальное хранилище ассетов (URL Higgsfield живёт 1 час → скачиваем к себе)
    media_dir: str = "./media"


settings = Settings()
