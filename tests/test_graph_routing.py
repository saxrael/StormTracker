"""Integration tests for reasoning_core routing and Google AI fallback."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agents.graph import reasoning_core
from app.state.state import AgentState


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
async def test_reasoning_core_invokes_openrouter_primary():
    """Verify that reasoning_core calls OpenRouter (Qwen) by default."""
    state = _create_sample_state()

    mock_google_bound = AsyncMock()
    mock_google_llm = MagicMock()
    mock_google_llm.bind_tools.return_value = mock_google_bound

    openrouter_response = AIMessage(content="Hello from OpenRouter Qwen!")
    mock_openrouter_bound = AsyncMock()
    mock_openrouter_bound.ainvoke.return_value = openrouter_response
    mock_openrouter_llm = MagicMock()
    mock_openrouter_llm.bind_tools.return_value = mock_openrouter_bound

    with (
        patch("app.agents.graph.get_openrouter_llm", return_value=mock_openrouter_llm),
        patch("app.agents.graph.get_gemma_llm", return_value=mock_google_llm),
    ):
        result = await reasoning_core(state)

        # 1. OpenRouter primary was invoked
        assert mock_openrouter_bound.ainvoke.called
        assert "OpenRouter Qwen" in result["messages"][0].content

        # 2. Google AI fallback was NOT invoked
        assert not mock_google_bound.ainvoke.called
        assert not mock_google_llm.bind_tools.called


@pytest.mark.asyncio
async def test_reasoning_core_fails_over_to_google_ai_on_openrouter_error():
    """Verify reasoning_core falls back to Google AI Gemma on OpenRouter error."""
    state = _create_sample_state()

    # OpenRouter raises an error (e.g. 429 quota exhaustion or service error)
    mock_openrouter_bound = AsyncMock()
    mock_openrouter_bound.ainvoke.side_effect = Exception(
        "429 Rate limit exceeded on OpenRouter"
    )
    mock_openrouter_llm = MagicMock()
    mock_openrouter_llm.bind_tools.return_value = mock_openrouter_bound

    # Google AI succeeds as fallback
    google_response = AIMessage(content="Hello from Google AI Gemma fallback!")
    mock_google_bound = AsyncMock()
    mock_google_bound.ainvoke.return_value = google_response
    mock_google_llm = MagicMock()
    mock_google_llm.bind_tools.return_value = mock_google_bound

    with (
        patch("app.agents.graph.get_openrouter_llm", return_value=mock_openrouter_llm),
        patch("app.agents.graph.get_gemma_llm", return_value=mock_google_llm),
    ):
        result = await reasoning_core(state)

        # 1. OpenRouter was attempted
        assert mock_openrouter_bound.ainvoke.called

        # 2. Google AI fallback was called and handled the request
        assert mock_google_bound.ainvoke.called
        assert "Google AI Gemma fallback" in result["messages"][0].content


@pytest.mark.asyncio
async def test_reasoning_core_no_cooldown_subsequent_request_tries_openrouter():
    """Verify no cooldown: subsequent requests still try OpenRouter first."""
    state = _create_sample_state()

    mock_openrouter_bound = AsyncMock()
    mock_openrouter_bound.ainvoke.return_value = AIMessage(
        content="OpenRouter fresh call"
    )
    mock_openrouter_llm = MagicMock()
    mock_openrouter_llm.bind_tools.return_value = mock_openrouter_bound

    mock_google_bound = AsyncMock()
    mock_google_llm = MagicMock()
    mock_google_llm.bind_tools.return_value = mock_google_bound

    with (
        patch("app.agents.graph.get_openrouter_llm", return_value=mock_openrouter_llm),
        patch("app.agents.graph.get_gemma_llm", return_value=mock_google_llm),
    ):
        result = await reasoning_core(state)
        assert mock_openrouter_bound.ainvoke.called
        assert not mock_google_bound.ainvoke.called
        assert "OpenRouter fresh call" in result["messages"][0].content


@pytest.mark.asyncio
async def test_reasoning_core_extracts_reasoning_content_thought():
    """Verify reasoning_content from Qwen is properly extracted into thoughts."""
    state = _create_sample_state()

    response_with_reasoning = AIMessage(
        content="Final answer for user",
        additional_kwargs={
            "reasoning_content": "Step 1: Check user role. Step 2: Greet user."
        },
    )
    mock_openrouter_bound = AsyncMock()
    mock_openrouter_bound.ainvoke.return_value = response_with_reasoning
    mock_openrouter_llm = MagicMock()
    mock_openrouter_llm.bind_tools.return_value = mock_openrouter_bound

    with patch("app.agents.graph.get_openrouter_llm", return_value=mock_openrouter_llm):
        result = await reasoning_core(state)
        msg_content = result["messages"][0].content
        assert "<thought>" in msg_content
        assert "Step 1: Check user role" in msg_content
        assert "Final answer for user" in msg_content


@pytest.mark.asyncio
async def test_reasoning_core_extracts_canonical_reasoning_thought():
    """Verify canonical OpenRouter reasoning field is extracted into thoughts."""
    state = _create_sample_state()

    response_with_reasoning = AIMessage(
        content="Musical guidance for user",
        additional_kwargs={
            "reasoning": "Step 1: Check interval history. Step 2: Suggest minor 2nd."
        },
    )
    mock_openrouter_bound = AsyncMock()
    mock_openrouter_bound.ainvoke.return_value = response_with_reasoning
    mock_openrouter_llm = MagicMock()
    mock_openrouter_llm.bind_tools.return_value = mock_openrouter_bound

    with patch(
        "app.agents.graph.get_openrouter_llm", return_value=mock_openrouter_llm
    ):
        result = await reasoning_core(state)
        msg_content = result["messages"][0].content
        assert "<thought>" in msg_content
        assert "Step 1: Check interval history" in msg_content
        assert "Musical guidance for user" in msg_content

