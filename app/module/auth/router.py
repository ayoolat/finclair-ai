import uuid
from typing import Optional

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import ApiResponse
from app.database.session import get_db
from app.module.auth.dependencies import AuthContext, get_auth_context
from app.module.auth.dto.auth import (
    ForgotPasscodeDto,
    LoginDto,
    LogoutDto,
    OnboardingGoalsDto,
    RefreshTokenDto,
    RegisterDto,
    ResendOtpDto,
    ResetPasscodeDto,
    SocialAuthDto,
    TokenPairResponseDto,
    VerifyEmailDto,
)
from app.module.auth.service.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=ApiResponse[dict])
async def register(dto: RegisterDto, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    result = await AuthService(db).register(dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=result.status_code, content=ApiResponse.ok(data=result.data, message="Registration successful. Check your email for the verification code.").model_dump())


@router.post("/verify-email", response_model=ApiResponse[TokenPairResponseDto])
async def verify_email(dto: VerifyEmailDto, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    result = await AuthService(db).verify_email(dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data, message="Email verified.").model_dump())


@router.post("/resend-otp", response_model=ApiResponse[dict])
async def resend_otp(dto: ResendOtpDto, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    result = await AuthService(db).resend_otp(dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.post("/login", response_model=ApiResponse[TokenPairResponseDto])
async def login(dto: LoginDto, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    result = await AuthService(db).login(dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data, message="Login successful.").model_dump())


@router.post("/refresh", response_model=ApiResponse[TokenPairResponseDto])
async def refresh(dto: RefreshTokenDto, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    result = await AuthService(db).refresh(dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.post("/logout", response_model=ApiResponse[dict])
async def logout(
    dto: Optional[LogoutDto] = Body(default=None),
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> JSONResponse:
    device_token = dto.device_token if dto else None
    result = await AuthService(db).logout(ctx.session_id, ctx.user_id, device_token)
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.post("/logout-all", response_model=ApiResponse[dict])
async def logout_all(
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> JSONResponse:
    result = await AuthService(db).logout_all(ctx.user_id)
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.post("/forgot-passcode", response_model=ApiResponse[dict])
async def forgot_passcode(dto: ForgotPasscodeDto, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    result = await AuthService(db).forgot_passcode(dto)
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.post("/reset-passcode", response_model=ApiResponse[TokenPairResponseDto])
async def reset_passcode(dto: ResetPasscodeDto, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    result = await AuthService(db).reset_passcode(dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data, message="Passcode reset successful.").model_dump())


@router.post("/social", response_model=ApiResponse[TokenPairResponseDto])
async def social_auth(dto: SocialAuthDto, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    result = await AuthService(db).social_auth(dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data, message="Authenticated.").model_dump())


@router.post("/onboarding/goals", response_model=ApiResponse[dict])
async def set_goals(
    dto: OnboardingGoalsDto,
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> JSONResponse:
    result = await AuthService(db).set_goals(ctx.user_id, dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())
