import asyncio
import secrets
import string

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

ph = PasswordHasher()

INVITE_TOKEN_ALPHABET = string.ascii_letters + string.digits


async def hash_passkey(plain_text: str) -> str:
    return await asyncio.to_thread(ph.hash, plain_text)


async def verify_passkey(plain_text: str, hashed_passkey: str) -> bool:
    def _verify():
        try:
            return ph.verify(hashed_passkey, plain_text)
        except VerifyMismatchError:
            return False

    return await asyncio.to_thread(_verify)


def generate_invite_token() -> str:
    prefix = "".join(secrets.choice(INVITE_TOKEN_ALPHABET) for _ in range(6))
    secret = "".join(secrets.choice(INVITE_TOKEN_ALPHABET) for _ in range(10))
    return f"{prefix}-{secret}"


async def check_rate_limit(chat_id: int, role: str) -> bool:
    from app.config import get_settings
    from app.services.database import redis_client

    settings = get_settings()
    key = f"rate_limit:{chat_id}"

    current_count = await redis_client.incr(key)
    if current_count == 1:
        await redis_client.expire(key, 60)

    limit = settings.RATE_LIMIT_REQUESTS if role in ["member", "admin", "root"] else 5
    return current_count <= limit
