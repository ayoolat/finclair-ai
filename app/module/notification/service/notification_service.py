import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.dto.pagination import PageQueryDto
from app.common.enums.notification import NotificationType
from app.common.response import PaginatedResponse, Result
from app.database.session import get_db
from app.module.notification.dto.notification import NotificationResponseDto, UnreadCountDto
from app.module.notification.schema.notification import Notification
from app.module.notification.service.push_service import PushService, get_push_service


class NotificationService:
    """
    Single entry point for the 5 events that get both an in-app (persisted) notification
    and a push: it writes the Notification row, then best-effort fires a push through the
    shared PushService (push failures are already swallowed/logged inside PushService, so
    they never block the caller's business logic).
    """

    def __init__(self, db: AsyncSession, push: PushService) -> None:
        self._db = db
        self._push = push

    async def notify(
        self,
        user_id: uuid.UUID,
        type: NotificationType,
        title: str,
        body: str,
        data: Optional[dict] = None,
    ) -> Notification:
        notification = Notification(
            user_id=user_id,
            type=type.value,
            title=title,
            body=body,
            data=data,
        )
        self._db.add(notification)
        await self._db.commit()
        await self._db.refresh(notification)

        await self._push.send_to_user(
            user_id, title=title, body=body, data={"type": type.value, **(data or {})}
        )
        return notification

    async def list_for_user(
        self, user_id: uuid.UUID, filters: PageQueryDto, unread_only: bool = False
    ) -> Result[PaginatedResponse[NotificationResponseDto]]:
        base = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            base = base.where(Notification.is_read.is_(False))

        total = (await self._db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

        result = await self._db.execute(
            base.order_by(Notification.created_at.desc()).offset(filters.offset).limit(filters.page_size)
        )
        dtos = [NotificationResponseDto.model_validate(n) for n in result.scalars().all()]
        return Result.ok(PaginatedResponse.ok(data=dtos, page=filters.page, page_size=filters.page_size, total=total))

    async def unread_count(self, user_id: uuid.UUID) -> Result[UnreadCountDto]:
        count = await self._db.scalar(
            select(func.count()).select_from(Notification).where(
                Notification.user_id == user_id, Notification.is_read.is_(False)
            )
        )
        return Result.ok(UnreadCountDto(count=count or 0))

    async def mark_read(self, user_id: uuid.UUID, notification_id: uuid.UUID) -> Result[NotificationResponseDto]:
        notification = await self._db.scalar(
            select(Notification).where(Notification.id == notification_id, Notification.user_id == user_id)
        )
        if notification is None:
            return Result.fail("Notification not found.", error_code="NOT_FOUND", status_code=404)

        if not notification.is_read:
            notification.is_read = True
            notification.read_at = datetime.now(timezone.utc)
            await self._db.commit()
            await self._db.refresh(notification)

        return Result.ok(NotificationResponseDto.model_validate(notification))

    async def mark_all_read(self, user_id: uuid.UUID) -> Result[None]:
        await self._db.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
            .values(is_read=True, read_at=datetime.now(timezone.utc))
        )
        await self._db.commit()
        return Result.ok(None)


def get_notification_service(
    db: AsyncSession = Depends(get_db),
    push: PushService = Depends(get_push_service),
) -> NotificationService:
    return NotificationService(db, push)
