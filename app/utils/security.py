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
