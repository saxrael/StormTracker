import secrets
import string

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

ph = PasswordHasher()

INVITE_TOKEN_ALPHABET = string.ascii_letters + string.digits
INVITE_TOKEN_LENGTH = 8


def hash_passkey(plain_text: str) -> str:
    return ph.hash(plain_text)


def verify_passkey(plain_text: str, hashed_passkey: str) -> bool:
    try:
        return ph.verify(hashed_passkey, plain_text)
    except VerifyMismatchError:
        return False


def generate_invite_token() -> str:
    return "".join(
        secrets.choice(INVITE_TOKEN_ALPHABET) for _ in range(INVITE_TOKEN_LENGTH)
    )


RATE_LIMIT_WINDOW_SECONDS = 60


async def check_rate_limit(chat_id: int) -> bool:
    from app.config import get_settings
    from app.services.database import redis_client

    settings = get_settings()
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
