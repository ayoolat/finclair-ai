import uuid

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import Result
from app.database.session import get_db
from app.module.notification.dto.notification import DeviceTokenResponseDto, RegisterDeviceTokenDto
from app.module.notification.schema.device_token import DeviceToken


class DeviceTokenService:
    """
    A user may be signed in on several devices at once, so tokens are keyed by
    the raw FCM/APNs token value rather than one-per-user: registering re-claims
    the token for the caller (handles device re-use across accounts), and each
    device is removed independently on logout — see AuthService.logout.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def register(
        self, user_id: uuid.UUID, dto: RegisterDeviceTokenDto
    ) -> Result[DeviceTokenResponseDto]:
        existing = await self._db.scalar(select(DeviceToken).where(DeviceToken.token == dto.token))
        if existing:
            existing.user_id = user_id
            existing.platform = dto.platform
            existing.is_active = True
            token_row = existing
        else:
            token_row = DeviceToken(user_id=user_id, token=dto.token, platform=dto.platform)
            self._db.add(token_row)

        await self._db.commit()
        await self._db.refresh(token_row)
        return Result.ok(DeviceTokenResponseDto.model_validate(token_row), status_code=201)

    async def list_tokens(self, user_id: uuid.UUID) -> Result[list[DeviceTokenResponseDto]]:
        rows = await self._db.execute(
            select(DeviceToken).where(DeviceToken.user_id == user_id, DeviceToken.is_active.is_(True))
        )
        return Result.ok([DeviceTokenResponseDto.model_validate(r) for r in rows.scalars().all()])

    async def unregister(self, user_id: uuid.UUID, token_id: uuid.UUID) -> Result[None]:
        token_row = await self._db.scalar(
            select(DeviceToken).where(DeviceToken.id == token_id, DeviceToken.user_id == user_id)
        )
        if token_row is None:
            return Result.fail("Device token not found.", error_code="NOT_FOUND", status_code=404)

        token_row.is_active = False
        await self._db.commit()
        return Result.ok(None)


def get_device_token_service(db: AsyncSession = Depends(get_db)) -> DeviceTokenService:
    return DeviceTokenService(db)
