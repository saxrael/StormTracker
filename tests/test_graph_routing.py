"""Integration tests for reasoning_core circuit breaker and failover routing."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.graph import reasoning_core
from app.services.circuit_breaker import (
    is_google_ai_in_cooldown,
    reset_google_ai_circuit_breaker,
)
from app.state.state import AgentState


@pytest.fixture(autouse=True)
async def reset_circuit():
    """Ensure circuit breaker is reset before each test."""
    await reset_google_ai_circuit_breaker()
    yield
    await reset_google_ai_circuit_breaker()


def _create_sample_state() -> AgentState:
    return {
        "messages": [HumanMessage(content="Hello assistant")],
        "chat_id": 12345,
        "user_id": 12345,
        "username": "testuser",
        "role": "member",
        "db_user_id": "00000000-0000-0000-0000-000000000001",
        "image_base64": None,
        "extracted_metrics": None,
        "image_vector": None,
        "full_name": "Test User",
        "is_onboarded": True,
        "conversation_summary": None,
        "relevant_facts": [],
        "task_status": "pending",
        "retry_count": 0,
        "critique": None,
    }


@pytest.mark.asyncio
async def test_reasoning_core_fails_over_to_openrouter_on_429():
    """Verify hitting 429 on Google AI trips circuit breaker and uses OpenRouter."""
    state = _create_sample_state()

    mock_google_bound = AsyncMock()
    mock_google_bound.ainvoke.side_effect = Exception(
        "429 RESOURCE_EXHAUSTED quota limit reached"
    )
    mock_google_llm = MagicMock()
    mock_google_llm.bind_tools.return_value = mock_google_bound

    openrouter_response = AIMessage(content="Hello from OpenRouter fallback!")
    mock_openrouter_bound = AsyncMock()
    mock_openrouter_bound.ainvoke.return_value = openrouter_response
    mock_openrouter_llm = MagicMock()
    mock_openrouter_llm.bind_tools.return_value = mock_openrouter_bound

    with (
        patch("app.agents.graph.get_gemma_llm", return_value=mock_google_llm),
        patch("app.agents.graph.get_openrouter_llm", return_value=mock_openrouter_llm),
    ):
        result = await reasoning_core(state)

        # 1. OpenRouter was called to seamlessly handle the message
        assert mock_openrouter_bound.ainvoke.called
        assert "OpenRouter fallback" in result["messages"][0].content

        # 2. Circuit breaker was tripped into 10-minute cooldown
        assert await is_google_ai_in_cooldown() is True


@pytest.mark.asyncio
async def test_reasoning_core_bypasses_google_ai_when_in_cooldown():
    """Verify that during cooldown, Google AI is not called and OpenRouter is used."""
    from app.services.circuit_breaker import trip_google_ai_circuit_breaker

    # Trip the circuit breaker
    await trip_google_ai_circuit_breaker("Simulated prior 429", cooldown_seconds=600)
    assert await is_google_ai_in_cooldown() is True

    state = _create_sample_state()

    mock_google_llm = MagicMock()
    openrouter_response = AIMessage(content="Direct OpenRouter response")
    mock_openrouter_bound = AsyncMock()
    mock_openrouter_bound.ainvoke.return_value = openrouter_response
    mock_openrouter_llm = MagicMock()
    mock_openrouter_llm.bind_tools.return_value = mock_openrouter_bound

    with (
        patch("app.agents.graph.get_gemma_llm", mock_google_llm),
        patch("app.agents.graph.get_openrouter_llm", return_value=mock_openrouter_llm),
    ):
        result = await reasoning_core(state)

        # Google AI must NOT be invoked at all
        assert not mock_google_llm.bind_tools.called
        assert not mock_google_llm.ainvoke.called

        # OpenRouter handled it directly
        assert mock_openrouter_bound.ainvoke.called
        assert "Direct OpenRouter response" in result["messages"][0].content
