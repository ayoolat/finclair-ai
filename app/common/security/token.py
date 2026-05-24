import uuid
from datetime import datetime, timedelta, timezone

from jose import jwt

from app.core.config import settings

_ALGORITHM = "HS256"


def create_access_token(user_id: uuid.UUID, session_id: uuid.UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode(
        {"sub": str(user_id), "sid": str(session_id), "exp": expire},
        settings.secret_key,
        algorithm=_ALGORITHM,
    )


def decode_token(token: str) -> tuple[uuid.UUID, uuid.UUID]:
    """
    Decode a JWT and return (user_id, session_id).
    Raises jose.JWTError on expiry or tampering.
    """
    payload = jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])
    return uuid.UUID(payload["sub"]), uuid.UUID(payload["sid"])
