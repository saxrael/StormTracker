"""Unit test for graph execution cancellation handling."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.graph import execute_graph
from app.state.state import AgentState


@pytest.mark.asyncio
async def test_execute_graph_handles_cancelled_error():
    """Test that execute_graph catches asyncio.CancelledError, notifies the user
    via Telegram, and re-raises CancelledError for proper task cancellation.
    """
    state: AgentState = {
        "messages": [],
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

    mock_send = AsyncMock()

    with (
        patch(
            "app.agents.graph._invoke_graph_with_retry",
            side_effect=asyncio.CancelledError("Task timed out"),
        ),
        patch(
            "app.agents.graph.TelegramService.send_message",
            mock_send,
        ),
    ):
        with pytest.raises(asyncio.CancelledError):
            await execute_graph(state, session_id="12345", raw_user_text="hello")

        # Verify notification sent explaining timeout/high-volume condition
        assert (
            mock_send.called
        ), "TelegramService.send_message was not called on cancellation!"
        call_args = mock_send.call_args
        assert call_args[1]["chat_id"] == 12345 or call_args[0][0] == 12345
        sent_text = call_args[1].get("text") or (
            call_args[0][1] if len(call_args[0]) > 1 else ""
        )
        assert (
            "timed out" in sent_text.lower() or "volume" in sent_text.lower()
        ), f"Expected timeout notification, got: {sent_text}"
