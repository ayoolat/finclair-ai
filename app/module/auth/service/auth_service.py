"""
Responsible for one thing: auth business flows.
Delegates to: hasher, token, OtpService, SessionService, email queue.
"""

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.email.service import enqueue_otp_email, enqueue_passcode_reset_email
from app.common.enums.user import OtpType
from app.core.config import settings
from app.common.response import Result
from app.common.security.hasher import hash_passcode, verify_passcode
from app.common.security.token import create_access_token
from app.module.auth.dto.auth import (
    ForgotPasscodeDto,
    LoginDto,
    OnboardingGoalsDto,
    RefreshTokenDto,
    RegisterDto,
    ResendOtpDto,
    ResetPasscodeDto,
    TokenPairResponseDto,
    VerifyEmailDto,
)
from app.module.auth.service.otp_service import OtpService
from app.module.auth.service.session_service import SessionService
from app.module.goal.schema.financial_goal import FinancialGoal
from app.module.user.schema.user import User
from app.module.user.schema.user_goal import UserGoal


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._otp = OtpService(db)
        self._sessions = SessionService(db)

    async def register(self, dto: RegisterDto) -> Result[dict]:
        if await self._email_exists(dto.email):
            return Result.fail("Email already registered.", error_code="EMAIL_TAKEN", status_code=409)
        if await self._username_exists(dto.username):
            return Result.fail("Username already taken.", error_code="USERNAME_TAKEN", status_code=409)

        user = User(
            email=dto.email,
            username=dto.username,
            hashed_passcode=hash_passcode(dto.passcode),
            default_currency=dto.default_currency,
        )
        self._db.add(user)
        await self._db.flush()

        otp = await self._otp.issue(user.id, OtpType.EMAIL_VERIFICATION)
        await self._db.commit()

        enqueue_otp_email(to=user.email, username=user.username, code=otp.code)
        payload: dict = {"message": "Verification code sent to your email."}
        if settings.debug:
            payload["otp"] = otp.code
        return Result.ok(payload, status_code=201)

    async def verify_email(self, dto: VerifyEmailDto) -> Result[TokenPairResponseDto]:
        user = await self._get_user_by_email(dto.email)
        if user is None:
            return Result.fail("User not found.", error_code="USER_NOT_FOUND", status_code=404)
        if user.is_email_verified:
            return Result.fail("Email already verified.", error_code="ALREADY_VERIFIED", status_code=409)

        otp = await self._otp.validate(user.id, dto.code, OtpType.EMAIL_VERIFICATION)
        if otp is None:
            return Result.fail("Invalid or expired code.", error_code="INVALID_OTP", status_code=400)

        user.is_email_verified = True
        otp.is_used = True
        session, raw_refresh = await self._sessions.create(user.id)
        await self._db.commit()

        return Result.ok(self._token_pair(user.id, session.id, raw_refresh))

    async def resend_otp(self, dto: ResendOtpDto) -> Result[dict]:
        user = await self._get_user_by_email(dto.email)
        if user is None:
            return Result.fail("User not found.", error_code="USER_NOT_FOUND", status_code=404)
        if user.is_email_verified:
            return Result.fail("Email already verified.", error_code="ALREADY_VERIFIED", status_code=409)

        otp = await self._otp.issue(user.id, OtpType.EMAIL_VERIFICATION)
        await self._db.commit()

        enqueue_otp_email(to=user.email, username=user.username, code=otp.code)
        payload: dict = {"message": "Verification code resent."}
        if settings.debug:
            payload["otp"] = otp.code
        return Result.ok(payload)

    async def login(self, dto: LoginDto) -> Result[TokenPairResponseDto]:
        user = await self._get_user_by_email(dto.email)

        if user is None or not verify_passcode(dto.passcode, user.hashed_passcode):
            return Result.fail("Invalid email or passcode.", error_code="INVALID_CREDENTIALS", status_code=401)
        if not user.is_active:
            return Result.fail("Account is inactive.", error_code="ACCOUNT_INACTIVE", status_code=403)
        if not user.is_email_verified:
            return Result.fail("Email not verified.", error_code="EMAIL_NOT_VERIFIED", status_code=403)

        session, raw_refresh = await self._sessions.create(user.id)
        await self._db.commit()

        return Result.ok(self._token_pair(user.id, session.id, raw_refresh))

    async def refresh(self, dto: RefreshTokenDto) -> Result[TokenPairResponseDto]:
        new_session, new_raw = await self._sessions.rotate(dto.refresh_token)
        if new_session is None:
            return Result.fail("Invalid or expired refresh token.", error_code="INVALID_REFRESH_TOKEN", status_code=401)

        await self._db.commit()
        return Result.ok(self._token_pair(new_session.user_id, new_session.id, new_raw))

    async def logout(self, session_id: uuid.UUID) -> Result[dict]:
        await self._sessions.revoke(session_id)
        await self._db.commit()
        return Result.ok({"message": "Logged out."})

    async def logout_all(self, user_id: uuid.UUID) -> Result[dict]:
        await self._sessions.revoke_all(user_id)
        await self._db.commit()
        return Result.ok({"message": "Logged out of all sessions."})

    async def forgot_passcode(self, dto: ForgotPasscodeDto) -> Result[dict]:
        user = await self._get_user_by_email(dto.email)
        if user is None:
            return Result.ok({"message": "If that email exists, a reset code has been sent."})

        otp = await self._otp.issue(user.id, OtpType.PASSCODE_RESET)
        await self._db.commit()

        enqueue_passcode_reset_email(to=user.email, username=user.username, code=otp.code)
        payload = {"message": "If that email exists, a reset code has been sent."}
        if settings.debug:
            payload["otp"] = otp.code
        return Result.ok(payload)

    async def reset_passcode(self, dto: ResetPasscodeDto) -> Result[TokenPairResponseDto]:
        user = await self._get_user_by_email(dto.email)
        if user is None:
            return Result.fail("User not found.", error_code="USER_NOT_FOUND", status_code=404)

        otp = await self._otp.validate(user.id, dto.code, OtpType.PASSCODE_RESET)
        if otp is None:
            return Result.fail("Invalid or expired code.", error_code="INVALID_OTP", status_code=400)

        user.hashed_passcode = hash_passcode(dto.new_passcode)
        otp.is_used = True
        session, raw_refresh = await self._sessions.create(user.id)
        await self._db.commit()

        return Result.ok(self._token_pair(user.id, session.id, raw_refresh))

    async def set_goals(self, user_id: uuid.UUID, dto: OnboardingGoalsDto) -> Result[dict]:
        result = await self._db.execute(select(User).where(User.id == user_id))
        if result.scalar_one_or_none() is None:
            return Result.fail("User not found.", error_code="USER_NOT_FOUND", status_code=404)

        goal_rows = await self._db.execute(
            select(FinancialGoal).where(FinancialGoal.id.in_(dto.goals))
        )
        found_goals = goal_rows.scalars().all()
        if len(found_goals) != len(dto.goals):
            return Result.fail("One or more goal IDs are invalid.", error_code="INVALID_GOALS", status_code=400)

        existing = await self._db.execute(select(UserGoal).where(UserGoal.user_id == user_id))
        for record in existing.scalars().all():
            await self._db.delete(record)

        for goal in found_goals:
            self._db.add(UserGoal(user_id=user_id, goal=goal.key))

        await self._db.commit()
        return Result.ok({"message": "Goals saved."})

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _token_pair(self, user_id: uuid.UUID, session_id: uuid.UUID, raw_refresh: str) -> TokenPairResponseDto:
        return TokenPairResponseDto(
            access_token=create_access_token(user_id, session_id),
            refresh_token=raw_refresh,
        )

    async def _get_user_by_email(self, email: str) -> Optional[User]:
        result = await self._db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def _email_exists(self, email: str) -> bool:
        result = await self._db.execute(select(User.id).where(User.email == email))
        return result.first() is not None

    async def _username_exists(self, username: str) -> bool:
        result = await self._db.execute(select(User.id).where(User.username == username))
        return result.first() is not None
