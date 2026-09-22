"""Unit tests for cognitive service LLM execution and Google AI fallback."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.config import get_settings
from app.services.cognitive_service import _execute_cognitive_llm_call


@pytest.mark.asyncio
async def test_execute_cognitive_llm_call_primary_success():
    """Verify that cognitive LLM call uses OpenRouter primary model on success."""
    settings = get_settings()
    mock_client = MagicMock()

    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Primary summary successfully generated."
    mock_response.choices = [mock_choice]

    messages = [
        {"role": "system", "content": "You are a test system."},
        {"role": "user", "content": "Extract summary."},
    ]

    with (
        patch(
            "app.services.cognitive_service._llm_call",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_llm_call,
        patch("app.services.cognitive_service.get_gemma_llm") as mock_get_gemma,
    ):
        result = await _execute_cognitive_llm_call(
            client=mock_client,
            messages=messages,
            temperature=0.2,
            max_tokens=500,
        )

        assert result == "Primary summary successfully generated."
        mock_llm_call.assert_awaited_once_with(
            client=mock_client,
            model=settings.OPENROUTER_MAIN_MODEL,
            messages=messages,
            temperature=0.2,
            max_tokens=500,
        )
        mock_get_gemma.assert_not_called()


@pytest.mark.asyncio
async def test_execute_cognitive_llm_call_fallback_on_primary_failure():
    """Verify fallback to Google AI Studio Gemma when OpenRouter call fails."""
    mock_client = MagicMock()

    messages = [
        {"role": "system", "content": "System prompt."},
        {"role": "user", "content": "User prompt."},
        {"role": "assistant", "content": "Assistant prompt."},
    ]

    mock_gemma_llm = MagicMock()
    mock_gemma_resp = AIMessage(content="Fallback summary from Gemma.")
    mock_gemma_llm.ainvoke = AsyncMock(return_value=mock_gemma_resp)

    with (
        patch(
            "app.services.cognitive_service._llm_call",
            new_callable=AsyncMock,
            side_effect=RuntimeError("OpenRouter 502 Bad Gateway"),
        ),
        patch(
            "app.services.cognitive_service.get_gemma_llm",
            return_value=mock_gemma_llm,
        ),
    ):
        result = await _execute_cognitive_llm_call(
            client=mock_client,
            messages=messages,
            temperature=0.2,
        )

        assert result == "Fallback summary from Gemma."
        mock_gemma_llm.ainvoke.assert_awaited_once()

        # Verify correct LangChain message conversion
        call_args = mock_gemma_llm.ainvoke.call_args[0][0]
        assert len(call_args) == 3
        assert isinstance(call_args[0], SystemMessage)
        assert call_args[0].content == "System prompt."
        assert isinstance(call_args[1], HumanMessage)
        assert call_args[1].content == "User prompt."
        assert isinstance(call_args[2], AIMessage)
        assert call_args[2].content == "Assistant prompt."


@pytest.mark.asyncio
async def test_execute_cognitive_llm_call_fallback_list_content():
    """Verify fallback handles list of content blocks gracefully."""
    mock_client = MagicMock()
    messages = [{"role": "user", "content": "Test prompt"}]

    mock_gemma_llm = MagicMock()
    mock_gemma_resp = MagicMock()
    mock_gemma_resp.content = [
        {"type": "text", "text": "Block 1."},
        "Block 2.",
    ]
    mock_gemma_llm.ainvoke = AsyncMock(return_value=mock_gemma_resp)

    with (
        patch(
            "app.services.cognitive_service._llm_call",
            new_callable=AsyncMock,
            side_effect=Exception("OpenRouter timeout"),
        ),
        patch(
            "app.services.cognitive_service.get_gemma_llm",
            return_value=mock_gemma_llm,
        ),
    ):
        result = await _execute_cognitive_llm_call(
            client=mock_client,
            messages=messages,
            temperature=0.1,
        )

        assert result == "Block 1. Block 2."
