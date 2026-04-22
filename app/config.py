from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    TELEGRAM_SECRET_TOKEN: str
    TELEGRAM_BOT_TOKEN: str
    WEBHOOK_URL: str

    GOOGLE_AI_API_KEY: str
    OPENROUTER_API_KEY: str

    DATABASE_URL: str
    REDIS_URL: str

    LANGFUSE_PUBLIC_KEY: str
    LANGFUSE_SECRET_KEY: str
    LANGFUSE_HOST: str

    CRON_SECRET: str
    ADMIN_CHAT_ID: int

    RATE_LIMIT_REQUESTS: int = 20
    IMAGE_SIMILARITY_THRESHOLD: float = 0.99


@lru_cache
def get_settings() -> Settings:
    return Settings()
