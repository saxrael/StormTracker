"""Unit tests for vector_service hybrid search SQL compilation."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.dialects.postgresql import asyncpg

from app.services.vector_service import hybrid_search_chat_history


@pytest.mark.unit
def test_hybrid_search_sql_parameter_binding():
    """Verify that all bind parameters in hybrid search SQL are recognized.

    Postgres typecasts like :vector::vector or :user_id::uuid must NOT
    prevent SQLAlchemy from extracting 'vector' and 'user_id' as bound parameters.
    """
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_session.execute.return_value = mock_result

    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "app.services.vector_service.async_session",
        return_value=mock_session_ctx,
    ):
        asyncio.run(
            hybrid_search_chat_history(
                db_user_id="00000000-0000-0000-0000-000000000001",
                query="test query",
                embedding=[0.1, 0.2, 0.3],
                limit=5,
            )
        )

    assert mock_session.execute.called
    stmt, _ = mock_session.execute.call_args[0]

    # Compile the statement for asyncpg dialect
    dialect = asyncpg.dialect()
    compiled = stmt.compile(dialect=dialect)

    # All four parameters must be recognized by SQLAlchemy
    assert (
        "user_id" in compiled.positiontup
    ), f"'user_id' not parsed! positiontup={compiled.positiontup}"
    assert (
        "vector" in compiled.positiontup
    ), f"'vector' not parsed! positiontup={compiled.positiontup}"
    assert (
        "query" in compiled.positiontup
    ), f"'query' not parsed! positiontup={compiled.positiontup}"
    assert (
        "limit" in compiled.positiontup
    ), f"'limit' not parsed! positiontup={compiled.positiontup}"

    # In compiled SQL, there should be NO uncompiled named parameters
    compiled_sql = compiled.string
    assert (
        ":vector" not in compiled_sql
    ), f"Found unparsed ':vector' in compiled SQL: {compiled_sql}"
    assert (
        ":user_id" not in compiled_sql
    ), f"Found unparsed ':user_id' in compiled SQL: {compiled_sql}"
