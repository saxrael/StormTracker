"""Unit tests for the Google AI circuit breaker and rate limit detection."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.circuit_breaker import (
    is_google_ai_in_cooldown,
    is_rate_limit_error,
    reset_google_ai_circuit_breaker,
    trip_google_ai_circuit_breaker,
)


@pytest.mark.asyncio
async def test_circuit_breaker_cooldown_lifecycle():
    """Verify circuit breaker lifecycle: idle -> tripped -> cooldown active -> reset."""
    mock_redis = AsyncMock()
    # Initially key does not exist
    mock_redis.get.return_value = None

    with patch("app.services.circuit_breaker.redis_client", mock_redis):
        # Reset memory state first
        await reset_google_ai_circuit_breaker()

        # 1. Initially NOT in cooldown
        assert await is_google_ai_in_cooldown() is False

        # 2. Trip circuit breaker with 600s cooldown
        await trip_google_ai_circuit_breaker(
            reason="429 RESOURCE_EXHAUSTED", cooldown_seconds=600
        )
        mock_redis.set.assert_called_once_with(
            "circuit_breaker:google_ai:cooldown",
            "tripped: 429 RESOURCE_EXHAUSTED",
            ex=600,
        )

        # 3. In cooldown while key exists
        mock_redis.get.return_value = b"tripped: 429 RESOURCE_EXHAUSTED"
        assert await is_google_ai_in_cooldown() is True

        # 4. Reset circuit breaker
        await reset_google_ai_circuit_breaker()
        mock_redis.get.return_value = None
        assert await is_google_ai_in_cooldown() is False


def test_is_rate_limit_error():
    """Verify rate limit detection across multiple error representations."""
    # Positive matches
    assert is_rate_limit_error(Exception("429 RESOURCE_EXHAUSTED")) is True
    assert is_rate_limit_error(Exception("Quota exceeded for metric")) is True
    assert is_rate_limit_error(Exception("Rate limit reached")) is True
    assert is_rate_limit_error(Exception("ResourceExhausted: free tier limit")) is True

    # Negative matches
    assert is_rate_limit_error(ValueError("Invalid parameter")) is False
    assert is_rate_limit_error(Exception("500 Internal Server Error")) is False
    assert is_rate_limit_error(KeyError("missing_key")) is False
