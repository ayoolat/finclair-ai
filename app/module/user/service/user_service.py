import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import Result
from app.module.user.dto.user import CreateUserDto, UserResponseDto
from app.module.user.schema.user import User


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, user_id: uuid.UUID) -> Result[UserResponseDto]:
        result = await self._db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user is None:
            return Result.fail("User not found.", error_code="USER_NOT_FOUND", status_code=404)

        return Result.ok(UserResponseDto.model_validate(user))

    async def get_by_email(self, email: str) -> Result[UserResponseDto]:
        result = await self._db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if user is None:
            return Result.fail("User not found.", error_code="USER_NOT_FOUND", status_code=404)

        return Result.ok(UserResponseDto.model_validate(user))

    async def create(self, dto: CreateUserDto, hashed_password: str) -> Result[UserResponseDto]:
        existing = await self._db.execute(select(User).where(User.email == dto.email))
        if existing.scalar_one_or_none() is not None:
            return Result.fail(
                "A user with this email already exists.",
                error_code="USER_ALREADY_EXISTS",
                status_code=409,
            )

        username_taken = await self._db.execute(
            select(User).where(User.username == dto.username)
        )
        if username_taken.scalar_one_or_none() is not None:
            return Result.fail(
                "This username is already taken.",
                error_code="USERNAME_TAKEN",
                status_code=409,
            )

        user = User(
            email=dto.email,
            username=dto.username,
            hashed_password=hashed_password,
            default_currency=dto.default_currency,
        )
        self._db.add(user)
        await self._db.commit()
        await self._db.refresh(user)

        return Result.ok(UserResponseDto.model_validate(user), status_code=201)
