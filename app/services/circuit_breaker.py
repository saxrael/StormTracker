"""Circuit breaker for Google AI Studio API rate limiting."""

import logging
import time

from app.services.database import redis_client

logger = logging.getLogger(__name__)

CIRCUIT_BREAKER_REDIS_KEY = "circuit_breaker:google_ai:cooldown"
_memory_cooldown_until: float = 0.0


async def is_google_ai_in_cooldown() -> bool:
    """Check if Google AI is currently in cooldown (circuit breaker OPEN)."""
    global _memory_cooldown_until
    now = time.time()

    # 1. Check Redis (shared across worker processes)
    try:
        val = await redis_client.get(CIRCUIT_BREAKER_REDIS_KEY)
        if val is not None:
            return True
    except Exception as exc:
        logger.debug(
            "Redis error checking circuit breaker, using memory fallback: %s",
            exc,
        )

    # 2. In-memory fallback
    return now < _memory_cooldown_until


async def trip_google_ai_circuit_breaker(
    reason: str = "429 Rate Limit", cooldown_seconds: int = 600
) -> None:
    """Trip the circuit breaker, placing Google AI into cooldown."""
    global _memory_cooldown_until
    _memory_cooldown_until = time.time() + cooldown_seconds

    logger.warning(
        "Tripping Google AI circuit breaker for %d seconds. Reason: %s",
        cooldown_seconds,
        reason,
    )

    try:
        await redis_client.set(
            CIRCUIT_BREAKER_REDIS_KEY,
            f"tripped: {reason}",
            ex=cooldown_seconds,
        )
    except Exception as exc:
        logger.warning(
            "Failed to set circuit breaker key in Redis (using in-memory fallback): %s",
            exc,
        )


async def reset_google_ai_circuit_breaker() -> None:
    """Reset the circuit breaker, clearing the cooldown state."""
    global _memory_cooldown_until
    _memory_cooldown_until = 0.0
    try:
        await redis_client.delete(CIRCUIT_BREAKER_REDIS_KEY)
    except Exception as exc:
        logger.debug("Failed to delete circuit breaker key from Redis: %s", exc)


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
