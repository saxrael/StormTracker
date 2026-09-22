from functools import lru_cache

from pydantic import ValidationInfo, field_validator
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
    DOMAIN_NAME: str

    GOOGLE_AI_API_KEY: str
    OPENROUTER_API_KEY: str

    DATABASE_URL: str
    REDIS_URL: str

    LANGFUSE_PUBLIC_KEY: str
    LANGFUSE_SECRET_KEY: str
    LANGFUSE_HOST: str

    CRON_SECRET: str
    ROOT_CLAIM_TOKEN: str | None = None

    RATE_LIMIT_REQUESTS: int = 20
    IMAGE_SIMILARITY_THRESHOLD: float = 0.99
    DEBUG: bool = False

    OPENROUTER_MAIN_MODEL: str = "qwen/qwen3.8-27b:free"
    GOOGLE_FALLBACK_MODEL: str = "gemma-4-31b-it"
    OPENROUTER_IMAGE_EMBEDDING_MODEL: str = (
        "nvidia/llama-nemotron-embed-vl-1b-v2:free"
    )
    OPENROUTER_TEXT_EMBEDDING_MODEL: str = (
        "nvidia/llama-nemotron-embed-vl-1b-v2:free"
    )
    OPENROUTER_REASONING_EFFORT: str = "medium"

    @field_validator(
        "OPENROUTER_MAIN_MODEL",
        "GOOGLE_FALLBACK_MODEL",
        "OPENROUTER_IMAGE_EMBEDDING_MODEL",
        "OPENROUTER_TEXT_EMBEDDING_MODEL",
        "OPENROUTER_REASONING_EFFORT",
        mode="before",
    )
    @classmethod
    def _fallback_empty_string(cls, v: str | None, info: ValidationInfo) -> str:
        if not v or not str(v).strip():
            defaults = {
                "OPENROUTER_MAIN_MODEL": "qwen/qwen3.8-27b:free",
                "GOOGLE_FALLBACK_MODEL": "gemma-4-31b-it",
                "OPENROUTER_IMAGE_EMBEDDING_MODEL": (
                    "nvidia/llama-nemotron-embed-vl-1b-v2:free"
                ),
                "OPENROUTER_TEXT_EMBEDDING_MODEL": (
                    "nvidia/llama-nemotron-embed-vl-1b-v2:free"
                ),
                "OPENROUTER_REASONING_EFFORT": "medium",
            }
            return defaults.get(info.field_name, v)
        return str(v).strip()


@lru_cache
def get_settings() -> Settings:
    return Settings()
