import logging
import uuid
from typing import Optional

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.firebase import send_push
from app.database.session import get_db
from app.module.notification.schema.device_token import DeviceToken

logger = logging.getLogger(__name__)


class PushService:
    """Sends push notifications to a user's registered devices via FCM."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def send_to_user(
        self,
        user_id: uuid.UUID,
        title: str,
        body: str,
        data: Optional[dict[str, str]] = None,
    ) -> None:
        rows = await self._db.execute(
            select(DeviceToken).where(DeviceToken.user_id == user_id, DeviceToken.is_active.is_(True))
        )
        tokens = list(rows.scalars().all())
        if not tokens:
            return

        try:
            response = send_push([t.token for t in tokens], title, body, data)
        except Exception as exc:
            logger.error("Push send failed for user %s: %s", user_id, exc)
            return

        if response is None:
            return

        # Prune tokens FCM rejected (uninstalled app, expired registration, etc.)
        # so future sends don't keep paying the round trip for a dead device.
        for token_row, single in zip(tokens, response.responses):
            if not single.success:
                token_row.is_active = False
        await self._db.commit()

    async def send_to_users(
        self,
        user_ids: list[uuid.UUID],
        title: str,
        body: str,
        data: Optional[dict[str, str]] = None,
    ) -> None:
        for user_id in user_ids:
            await self.send_to_user(user_id, title, body, data)


def get_push_service(db: AsyncSession = Depends(get_db)) -> PushService:
    return PushService(db)
