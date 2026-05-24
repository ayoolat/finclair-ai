from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import ApiResponse
from app.database.session import get_db
from app.module.auth.dto.auth import LoginDto, RegisterDto, TokenResponseDto
from app.module.auth.service.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=ApiResponse[TokenResponseDto])
async def register(dto: RegisterDto, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    result = await AuthService(db).register(dto)

    if result.is_err:
        return JSONResponse(
            status_code=result.status_code,
            content=ApiResponse.error(result.error or "Registration failed.").model_dump(),
        )

    return JSONResponse(
        status_code=result.status_code,
        content=ApiResponse.ok(data=result.data, message="Registration successful.").model_dump(),
    )


@router.post("/login", response_model=ApiResponse[TokenResponseDto])
async def login(dto: LoginDto, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    result = await AuthService(db).login(dto)

    if result.is_err:
        return JSONResponse(
            status_code=result.status_code,
            content=ApiResponse.error(result.error or "Login failed.").model_dump(),
        )

    return JSONResponse(
        status_code=result.status_code,
        content=ApiResponse.ok(data=result.data, message="Login successful.").model_dump(),
    )
