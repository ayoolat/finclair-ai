import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response import ApiResponse
from app.database.session import get_db
from app.module.user.dto.user import UserResponseDto
from app.module.user.service.user_service import UserService

router = APIRouter(prefix="/user", tags=["user"])


@router.get("/{user_id}", response_model=ApiResponse[UserResponseDto])
async def get_user(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    result = await UserService(db).get_by_id(user_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error or "User not found.").model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())
