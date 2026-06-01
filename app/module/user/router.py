from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import ApiResponse
from app.database.session import get_db
from app.module.auth.dependencies import AuthContext, get_auth_context
from app.module.user.dto.user import UserResponseDto
from app.module.user.service.user_service import UserService

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/check-username", response_model=ApiResponse[dict])
async def check_username(
    username: str = Query(..., min_length=1, max_length=50),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    available = await UserService(db).username_available(username)
    return JSONResponse(
        status_code=200,
        content=ApiResponse.ok(data={"username": username.strip().lower(), "available": available}).model_dump(),
    )


@router.get("/me", response_model=ApiResponse[UserResponseDto])
async def get_me(
    db: AsyncSession = Depends(get_db),
    ctx: AuthContext = Depends(get_auth_context),
) -> JSONResponse:
    result = await UserService(db).get_by_id(ctx.user_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error or "User not found.").model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())
