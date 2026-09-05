"""Unit tests for LLM setup, fast-fail retries, and OpenRouter integration."""

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.agents.llm_setup import get_gemma_llm, get_openrouter_llm
from app.config import get_settings


def test_get_gemma_llm_configured_with_zero_retries():
    """Verify that Google AI is configured with max_retries=0 to fast-fail on 429."""
    llm = get_gemma_llm()
    assert isinstance(llm, ChatGoogleGenerativeAI)
    assert llm.max_retries == 0


def test_get_openrouter_llm_configured_correctly():
    """Verify OpenRouter fallback model configuration and base URL."""
    settings = get_settings()
    llm = get_openrouter_llm()
    assert isinstance(llm, ChatOpenAI)
    assert llm.model_name == settings.OPENROUTER_FALLBACK_MODEL
    assert "openrouter.ai" in str(llm.openai_api_base)
