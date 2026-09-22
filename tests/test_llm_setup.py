"""Unit tests for LLM setup, model configurations, and embeddings."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.agents.llm_setup import (
    get_gemma_llm,
    get_image_embedding,
    get_openrouter_llm,
    get_text_embedding,
)
from app.config import Settings, get_settings


def test_get_gemma_llm_configured_as_fallback():
    """Verify that Google AI is configured as fallback model with max_retries=0."""
    settings = get_settings()
    llm = get_gemma_llm()
    assert isinstance(llm, ChatGoogleGenerativeAI)
    assert llm.model == settings.GOOGLE_FALLBACK_MODEL
    assert llm.max_retries == 0


def test_get_openrouter_llm_configured_as_primary():
    """Verify OpenRouter primary model configuration and base URL."""
    settings = get_settings()
    llm = get_openrouter_llm()
    assert isinstance(llm, ChatOpenAI)
    assert llm.model_name == settings.OPENROUTER_MAIN_MODEL
    assert "openrouter.ai" in str(llm.openai_api_base)
    assert llm.extra_body == {
        "reasoning": {"effort": settings.OPENROUTER_REASONING_EFFORT}
    }


def test_get_gemma_llm_custom_model_override():
    """Verify get_gemma_llm accepts a custom model override."""
    llm = get_gemma_llm(model="custom-gemma-model")
    assert isinstance(llm, ChatGoogleGenerativeAI)
    assert llm.model == "custom-gemma-model"


def test_get_openrouter_llm_custom_model_override():
    """Verify get_openrouter_llm accepts a custom model override."""
    llm = get_openrouter_llm(model="custom/qwen-override")
    assert isinstance(llm, ChatOpenAI)
    assert llm.model_name == "custom/qwen-override"


@pytest.mark.asyncio
async def test_get_image_embedding_uses_configured_model():
    """Verify get_image_embedding uses OPENROUTER_IMAGE_EMBEDDING_MODEL."""
    settings = get_settings()
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_item = MagicMock()
    mock_item.embedding = [0.11, 0.22, 0.33]
    mock_resp.data = [mock_item]
    mock_client.embeddings.create = AsyncMock(return_value=mock_resp)

    with patch(
        "app.agents.llm_setup._get_openrouter_client",
        return_value=mock_client,
    ):
        embedding = await get_image_embedding("mock_base64_data")

        assert embedding == [0.11, 0.22, 0.33]
        mock_client.embeddings.create.assert_awaited_once()
        _, kwargs = mock_client.embeddings.create.call_args
        assert kwargs["model"] == settings.OPENROUTER_IMAGE_EMBEDDING_MODEL


@pytest.mark.asyncio
async def test_get_text_embedding_uses_configured_model():
    """Verify get_text_embedding uses OPENROUTER_TEXT_EMBEDDING_MODEL."""
    settings = get_settings()
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_item = MagicMock()
    mock_item.embedding = [0.44, 0.55, 0.66]
    mock_resp.data = [mock_item]
    mock_client.embeddings.create = AsyncMock(return_value=mock_resp)

    with patch(
        "app.agents.llm_setup._get_openrouter_client",
        return_value=mock_client,
    ):
        embedding = await get_text_embedding("test musical fact")

        assert embedding == [0.44, 0.55, 0.66]
        mock_client.embeddings.create.assert_awaited_once()
        _, kwargs = mock_client.embeddings.create.call_args
        assert kwargs["model"] == settings.OPENROUTER_TEXT_EMBEDDING_MODEL
        assert kwargs["input"] == "test musical fact"


def test_settings_empty_string_model_fallback():
    """Verify empty or whitespace strings fall back to safe default models."""
    s = Settings(
        TELEGRAM_SECRET_TOKEN="dummy",
        TELEGRAM_BOT_TOKEN="dummy",
        WEBHOOK_URL="https://example.com",
        DOMAIN_NAME="example.com",
        GOOGLE_AI_API_KEY="dummy",
        OPENROUTER_API_KEY="dummy",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/db",
        REDIS_URL="redis://localhost:6379/0",
        LANGFUSE_PUBLIC_KEY="dummy",
        LANGFUSE_SECRET_KEY="dummy",
        LANGFUSE_HOST="https://cloud.langfuse.com",
        CRON_SECRET="dummy",
        OPENROUTER_MAIN_MODEL="   ",
        GOOGLE_FALLBACK_MODEL="",
        OPENROUTER_IMAGE_EMBEDDING_MODEL="",
        OPENROUTER_TEXT_EMBEDDING_MODEL="   ",
        OPENROUTER_REASONING_EFFORT="",
    )
    assert s.OPENROUTER_MAIN_MODEL == "qwen/qwen3.8-27b:free"
    assert s.GOOGLE_FALLBACK_MODEL == "gemma-4-31b-it"
    assert (
        s.OPENROUTER_IMAGE_EMBEDDING_MODEL
        == "nvidia/llama-nemotron-embed-vl-1b-v2:free"
    )
    assert (
        s.OPENROUTER_TEXT_EMBEDDING_MODEL
        == "nvidia/llama-nemotron-embed-vl-1b-v2:free"
    )
    assert s.OPENROUTER_REASONING_EFFORT == "medium"


def test_settings_custom_model_overrides():
    """Verify non-empty custom model strings override defaults cleanly."""
    s = Settings(
        TELEGRAM_SECRET_TOKEN="dummy",
        TELEGRAM_BOT_TOKEN="dummy",
        WEBHOOK_URL="https://example.com",
        DOMAIN_NAME="example.com",
        GOOGLE_AI_API_KEY="dummy",
        OPENROUTER_API_KEY="dummy",
        DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/db",
        REDIS_URL="redis://localhost:6379/0",
        LANGFUSE_PUBLIC_KEY="dummy",
        LANGFUSE_SECRET_KEY="dummy",
        LANGFUSE_HOST="https://cloud.langfuse.com",
        CRON_SECRET="dummy",
        OPENROUTER_MAIN_MODEL="custom/qwen-max",
        GOOGLE_FALLBACK_MODEL="custom-gemma-ultra",
        OPENROUTER_IMAGE_EMBEDDING_MODEL="custom/vl-embed",
        OPENROUTER_TEXT_EMBEDDING_MODEL="custom/text-embed",
        OPENROUTER_REASONING_EFFORT="high",
    )
    assert s.OPENROUTER_MAIN_MODEL == "custom/qwen-max"
    assert s.GOOGLE_FALLBACK_MODEL == "custom-gemma-ultra"
    assert s.OPENROUTER_IMAGE_EMBEDDING_MODEL == "custom/vl-embed"
    assert s.OPENROUTER_TEXT_EMBEDDING_MODEL == "custom/text-embed"
    assert s.OPENROUTER_REASONING_EFFORT == "high"
