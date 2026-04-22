import redis.asyncio as aioredis

from app.config import get_settings

settings = get_settings()

redis_client = aioredis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
)

RATE_LIMIT_WINDOW_SECONDS = 60


async def check_rate_limit(chat_id: int) -> bool:
    key = f"rate_limit:{chat_id}"

    async with redis_client.pipeline(transaction=True) as pipe:
        pipe.incr(key)
        pipe.ttl(key)
        results = await pipe.execute()

    current_count: int = results[0]
    current_ttl: int = results[1]

    if current_ttl == -1:
        await redis_client.expire(key, RATE_LIMIT_WINDOW_SECONDS)

    return current_count <= settings.RATE_LIMIT_REQUESTS
