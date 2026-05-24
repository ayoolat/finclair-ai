"""
Responsible for one thing: extracting and validating the current user from a request.
"""

import uuid
from dataclasses import dataclass

from fastapi import Header, HTTPException
from jose import JWTError

from app.common.security.token import decode_token


@dataclass
class AuthContext:
    user_id: uuid.UUID
    session_id: uuid.UUID


def get_auth_context(authorization: str = Header(...)) -> AuthContext:
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError
        user_id, session_id = decode_token(token)
        return AuthContext(user_id=user_id, session_id=session_id)
    except (JWTError, ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
