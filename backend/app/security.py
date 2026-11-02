import hashlib
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app.config import settings

ACCESS_COOKIE = "access_token"
ALGORITHM = "HS256"

_password_hasher = PasswordHash.recommended()  # Argon2


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hasher.verify(password, password_hash)


def password_fingerprint(password_hash: str) -> str:
    """A short value that changes whenever the password changes."""
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def create_token(
    user_id: int,
    purpose: str,
    expires_minutes: int,
    fingerprint: str | None = None,
) -> str:
    payload = {
        "sub": str(user_id),
        "purpose": purpose,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
    }
    if fingerprint:
        payload["fp"] = fingerprint
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str, purpose: str) -> dict | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("purpose") != purpose:
        return None
    if not str(payload.get("sub", "")).isdigit():
        return None
    return payload
