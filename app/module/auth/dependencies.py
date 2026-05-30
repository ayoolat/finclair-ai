"""
Responsible for one thing: extracting and validating the current user from a request.
"""

import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from app.common.security.token import decode_token

_bearer = HTTPBearer()


@dataclass
class AuthContext:
    user_id: uuid.UUID
    session_id: uuid.UUID


def get_auth_context(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> AuthContext:
    try:
        user_id, session_id = decode_token(credentials.credentials)
        return AuthContext(user_id=user_id, session_id=session_id)
    except (JWTError, ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
