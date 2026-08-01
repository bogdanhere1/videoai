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

    # native | segmind | fal | eachlabs
    video_provider: str = "native"
    higgsfield_api_key: str = ""
    higgsfield_base_url: str = "https://cloud.higgsfield.ai"

    elevenlabs_api_key: str = ""


settings = Settings()
