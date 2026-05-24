"""
Responsible for one thing: refresh token session lifecycle —
create, validate, rotate, and revoke sessions.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.module.auth.schema.session import Session


def _generate_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def _hash_token(raw: str) -> str:
    # SHA-256 is appropriate here — refresh tokens are high-entropy random values,
    # not user-chosen passwords, so bcrypt's slow hashing is unnecessary.
    return hashlib.sha256(raw.encode()).hexdigest()


class SessionService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        user_id: uuid.UUID,
        *,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> tuple[Session, str]:
        """
        Create a new session. Returns (session, raw_refresh_token).
        The raw token is returned once and never stored — only its hash is persisted.
        """
        raw = _generate_refresh_token()
        session = Session(
            user_id=user_id,
            token_hash=_hash_token(raw),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days),
            created_at=datetime.now(timezone.utc),
            user_agent=user_agent,
            ip_address=ip_address,
        )
        self._db.add(session)
        return session, raw

    async def rotate(
        self, raw_token: str
    ) -> tuple[Optional[Session], Optional[str]]:
        """
        Validate an incoming refresh token, revoke it, and issue a new one.
        Returns (new_session, new_raw_token) or (None, None) if invalid.
        """
        session = await self._find_valid(raw_token)
        if session is None:
            return None, None

        session.is_revoked = True

        new_session, new_raw = await self.create(
            session.user_id,
            user_agent=session.user_agent,
            ip_address=session.ip_address,
        )
        return new_session, new_raw

    async def revoke(self, session_id: uuid.UUID) -> None:
        """Revoke a single session (logout this device)."""
        await self._db.execute(
            update(Session)
            .where(Session.id == session_id)
            .values(is_revoked=True)
        )

    async def revoke_all(self, user_id: uuid.UUID) -> None:
        """Revoke all active sessions for a user (logout everywhere)."""
        await self._db.execute(
            update(Session)
            .where(Session.user_id == user_id, Session.is_revoked == False)  # noqa: E712
            .values(is_revoked=True)
        )

    async def _find_valid(self, raw_token: str) -> Optional[Session]:
        result = await self._db.execute(
            select(Session).where(
                Session.token_hash == _hash_token(raw_token),
                Session.is_revoked == False,  # noqa: E712
                Session.expires_at > datetime.now(timezone.utc),
            )
        )
        return result.scalar_one_or_none()
