"""
Responsible for one thing: OTP lifecycle — generate, persist, validate, fetch.
Has no knowledge of email delivery or auth business rules.
"""

import random
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums.user import OtpType
from app.core.config import settings
from app.module.auth.schema.otp_token import OtpToken


class OtpService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def issue(self, user_id: uuid.UUID, otp_type: OtpType) -> OtpToken:
        """Create and persist a new OTP. Does not commit — caller controls the transaction."""
        token = OtpToken(
            user_id=user_id,
            code="".join(random.choices(string.digits, k=6)),
            otp_type=otp_type.value,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expire_minutes),
            created_at=datetime.now(timezone.utc),
        )
        self._db.add(token)
        return token

    async def validate(
        self, user_id: uuid.UUID, code: str, otp_type: OtpType
    ) -> Optional[OtpToken]:
        """Return the matching unused, unexpired OTP or None."""
        result = await self._db.execute(
            select(OtpToken).where(
                OtpToken.user_id == user_id,
                OtpToken.code == code,
                OtpToken.otp_type == otp_type.value,
                OtpToken.is_used == False,  # noqa: E712
                OtpToken.expires_at > datetime.now(timezone.utc),
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_code(self, user_id: uuid.UUID, otp_type: OtpType) -> str:
        """Fetch the code from the most recently issued OTP of a given type."""
        result = await self._db.execute(
            select(OtpToken)
            .where(OtpToken.user_id == user_id, OtpToken.otp_type == otp_type.value)
            .order_by(OtpToken.created_at.desc())
            .limit(1)
        )
        token = result.scalar_one_or_none()
        return token.code if token else ""
