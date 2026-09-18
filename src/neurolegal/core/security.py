"""Password hashing and opaque-token primitives shared by services.

Pure functions over argon2/sha256 — no models, no FastAPI, no domain types.
Session/verify/reset tokens are opaque: the raw token lives only in the
cookie or the emailed link, the DB stores its sha256 hex.
"""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

_hasher = PasswordHasher()  # argon2id with library-recommended parameters


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except (VerifyMismatchError, VerificationError, ValueError):
        # Wrong password or a corrupted/foreign hash value — fail closed.
        return False


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
