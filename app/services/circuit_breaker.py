"""Resilience and error classification for LLM API providers."""

import logging

logger = logging.getLogger(__name__)


def is_rate_limit_error(exc: Exception) -> bool:
    """Check if an exception indicates a rate limit or quota exhaustion (429)."""
    err_str = str(exc)
    err_lower = err_str.lower()
    return (
        "429" in err_str
        or "resource_exhausted" in err_lower
        or "resourceexhausted" in err_lower
        or "quota exceeded" in err_lower
        or "rate limit" in err_lower
    )


def is_transient_error(exc: Exception) -> bool:
    """Check if an exception indicates a transient error for retry/failover."""
    err_str = str(exc)
    err_lower = err_str.lower()
    return (
        is_rate_limit_error(exc)
        or "500" in err_str
        or "502" in err_str
        or "503" in err_str
        or "504" in err_str
        or "timeout" in err_lower
        or "connection" in err_lower
        or "overloaded" in err_lower
    )
