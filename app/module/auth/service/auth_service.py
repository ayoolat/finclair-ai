from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import Result
from app.core.config import settings
from app.module.auth.dto.auth import LoginDto, RegisterDto, TokenResponseDto
from app.module.user.dto.user import CreateUserDto
from app.module.user.schema.user import User
from app.module.user.service.user_service import UserService

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


def _hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def _verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def _create_access_token(subject: str, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._user_service = UserService(db)

    async def register(self, dto: RegisterDto) -> Result[TokenResponseDto]:
        create_dto = CreateUserDto(
            email=dto.email,
            username=dto.username,
            password=dto.password,
            default_currency=dto.default_currency,
        )
        user_result = await self._user_service.create(
            create_dto, _hash_password(dto.password)
        )

        if user_result.is_err:
            return Result.fail(
                user_result.error or "Registration failed.",
                error_code=user_result.error_code,
                status_code=user_result.status_code,
            )

        token = _create_access_token(str(user_result.data.id))  # type: ignore[union-attr]
        return Result.ok(TokenResponseDto(access_token=token), status_code=201)

    async def login(self, dto: LoginDto) -> Result[TokenResponseDto]:
        result = await self._db.execute(select(User).where(User.email == dto.email))
        user = result.scalar_one_or_none()

        if user is None or not _verify_password(dto.password, user.hashed_password):
            return Result.fail(
                "Invalid email or password.",
                error_code="INVALID_CREDENTIALS",
                status_code=401,
            )

        if not user.is_active:
            return Result.fail(
                "Account is inactive.", error_code="ACCOUNT_INACTIVE", status_code=403
            )

        token = _create_access_token(str(user.id))
        return Result.ok(TokenResponseDto(access_token=token))
