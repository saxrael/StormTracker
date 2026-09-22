"""Unit tests for LLM resilience error classification and rate limit detection."""

from app.services.circuit_breaker import (
    is_rate_limit_error,
    is_transient_error,
)


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


def test_is_transient_error():
    """Verify transient error classification for exponential backoff."""
    # Rate limits and quotas
    assert is_transient_error(Exception("429 Too Many Requests")) is True
    assert is_transient_error(Exception("ResourceExhausted")) is True

    # Server errors
    assert is_transient_error(Exception("500 Internal Server Error")) is True
    assert is_transient_error(Exception("502 Bad Gateway")) is True
    assert is_transient_error(Exception("503 Service Unavailable")) is True
    assert is_transient_error(Exception("504 Gateway Timeout")) is True

    # Network / connection issues
    assert is_transient_error(Exception("Request timeout after 30s")) is True
    assert is_transient_error(Exception("Connection reset by peer")) is True
    assert is_transient_error(Exception("Server overloaded")) is True

    # Non-transient errors
    assert is_transient_error(ValueError("Bad input")) is False
    assert is_transient_error(KeyError("missing_field")) is False
