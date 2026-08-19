"""Integration tests for LangGraph agent multi-signal deduplication pipeline."""

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from app.agents.graph import tool_executor
from app.state.state import AgentState


@pytest.mark.asyncio
async def test_exact_image_duplicate_rejection(
    sample_png_b64, sample_intervals_metrics_90
):
    """Test that submitting an exact duplicate image file is caught immediately."""
    state: AgentState = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "MetricExtractionSchema",
                        "args": sample_intervals_metrics_90,
                        "id": "call_exact_dup_1",
                    }
                ],
            )
        ],
        "chat_id": 12345,
        "user_id": 12345,
        "username": "testuser",
        "role": "member",
        "db_user_id": "00000000-0000-0000-0000-000000000001",
        "image_base64": sample_png_b64,
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

    with patch(
        "app.agents.graph.fraud_service.check_exact_image_duplicate",
        new_callable=AsyncMock,
    ) as mock_exact:
        mock_exact.return_value = True

        result = await tool_executor(state)
        messages = result["messages"]
        assert len(messages) == 1
        assert (
            "Fraud detected: Duplicate screenshot image file already submitted"
            in messages[0].content
        )


@pytest.mark.asyncio
async def test_legitimate_different_submission_passes(
    sample_png_b64, sample_intervals_metrics_90
):
    """Test that a clean, legitimate submission passes all fraud checks
    and commits to database."""
    state: AgentState = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "MetricExtractionSchema",
                        "args": sample_intervals_metrics_90,
                        "id": "call_legit_1",
                    }
                ],
            )
        ],
        "chat_id": 12345,
        "user_id": 12345,
        "username": "testuser",
        "role": "member",
        "db_user_id": "00000000-0000-0000-0000-000000000001",
        "image_base64": sample_png_b64,
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

    with (
        patch(
            "app.agents.graph.fraud_service.check_exact_image_duplicate",
            new_callable=AsyncMock,
        ) as mock_exact,
        patch(
            "app.agents.graph.fraud_service.check_metadata_duplicate",
            new_callable=AsyncMock,
        ) as mock_meta,
        patch(
            "app.agents.graph.fraud_service.check_visual_duplicate",
            new_callable=AsyncMock,
        ) as mock_visual,
        patch(
            "app.agents.graph.get_image_embedding", new_callable=AsyncMock
        ) as mock_emb,
        patch("app.agents.graph.async_session") as mock_session_ctx,
    ):
        mock_exact.return_value = False
        mock_meta.return_value = False
        mock_visual.return_value = 0.85
        mock_emb.return_value = [0.1] * 2048

        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_result.scalar_one.return_value = "00000000-0000-0000-0000-000000000001"
        mock_session.execute.return_value = mock_result
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        result = await tool_executor(state)
        messages = result["messages"]
        assert len(messages) == 1
        assert "Fraud detected" not in messages[0].content
        assert "Intervals" in messages[0].content


@pytest.mark.asyncio
async def test_na_metadata_is_not_flagged(sample_png_b64, sample_na_metadata_metrics):
    """Test that cropped or unreadable status bar metadata ('N/A')
    does not trigger fraud."""
    state: AgentState = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "MetricExtractionSchema",
                        "args": sample_na_metadata_metrics,
                        "id": "call_na_meta_1",
                    }
                ],
            )
        ],
        "chat_id": 12345,
        "user_id": 12345,
        "username": "testuser",
        "role": "member",
        "db_user_id": "00000000-0000-0000-0000-000000000001",
        "image_base64": sample_png_b64,
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

    with (
        patch(
            "app.agents.graph.fraud_service.check_exact_image_duplicate",
            new_callable=AsyncMock,
        ) as mock_exact,
        patch(
            "app.agents.graph.fraud_service.check_metadata_duplicate",
            new_callable=AsyncMock,
        ) as mock_meta,
        patch(
            "app.agents.graph.fraud_service.check_visual_duplicate",
            new_callable=AsyncMock,
        ) as mock_visual,
        patch(
            "app.agents.graph.get_image_embedding", new_callable=AsyncMock
        ) as mock_emb,
        patch("app.agents.graph.async_session") as mock_session_ctx,
    ):
        mock_exact.return_value = False
        mock_visual.return_value = 0.50
        mock_emb.return_value = [0.1] * 2048

        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_result.scalar_one.return_value = "00000000-0000-0000-0000-000000000001"
        mock_session.execute.return_value = mock_result
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        result = await tool_executor(state)
        # Verify check_metadata_duplicate was NOT called because
        # is_valid_device_metadata returned False
        assert mock_meta.call_count == 0
        messages = result["messages"]
        assert len(messages) == 1
        assert "Fraud detected" not in messages[0].content


@pytest.mark.asyncio
async def test_visual_duplicate_flagged_when_similarity_exceeds_threshold(
    sample_png_b64, sample_intervals_metrics_90
):
    """Test that visual duplicate is flagged when similarity exceeds
    threshold on matching metrics."""
    state: AgentState = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "MetricExtractionSchema",
                        "args": sample_intervals_metrics_90,
                        "id": "call_visual_dup_1",
                    }
                ],
            )
        ],
        "chat_id": 12345,
        "user_id": 12345,
        "username": "testuser",
        "role": "member",
        "db_user_id": "00000000-0000-0000-0000-000000000001",
        "image_base64": sample_png_b64,
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

    with (
        patch(
            "app.agents.graph.fraud_service.check_exact_image_duplicate",
            new_callable=AsyncMock,
        ) as mock_exact,
        patch(
            "app.agents.graph.fraud_service.check_metadata_duplicate",
            new_callable=AsyncMock,
        ) as mock_meta,
        patch(
            "app.agents.graph.fraud_service.check_visual_duplicate",
            new_callable=AsyncMock,
        ) as mock_visual,
        patch(
            "app.agents.graph.get_image_embedding", new_callable=AsyncMock
        ) as mock_emb,
        patch("app.agents.graph.async_session") as mock_session_ctx,
    ):
        mock_exact.return_value = False
        mock_meta.return_value = False
        mock_visual.return_value = 0.999
        mock_emb.return_value = [0.1] * 2048

        mock_session = AsyncMock()
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        result = await tool_executor(state)
        messages = result["messages"]
        assert len(messages) == 1
        assert "Fraud detected: Image is a visual duplicate." in messages[0].content
