"""Password hashing and cryptographically random, opaque session credentials."""

from hashlib import sha256
from secrets import token_urlsafe

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

password_hash = PasswordHash.recommended()
# Missing accounts still perform the same expensive password verification.
DUMMY_HASH = password_hash.hash(token_urlsafe(32))


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return password_hash.verify(password, encoded)
    except (UnknownHashError, ValueError):
        return False


def new_token() -> str:
    return token_urlsafe(32)


def digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()
