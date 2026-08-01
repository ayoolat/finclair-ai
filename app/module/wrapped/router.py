from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.common.response import ApiResponse
from app.module.auth.dependencies import AuthContext, get_auth_context
from app.module.wrapped.dto.wrapped import WrappedDto
from app.module.wrapped.service.wrapped_service import WrappedService, get_wrapped_service

router = APIRouter(prefix="/wrapped", tags=["wrapped"])


@router.get("", response_model=ApiResponse[WrappedDto])
async def get_wrapped(
    year: Optional[int] = Query(None, description="Calendar year to wrap. Defaults to the current year."),
    ctx: AuthContext = Depends(get_auth_context),
    service: WrappedService = Depends(get_wrapped_service),
) -> JSONResponse:
    result = await service.get_wrapped(ctx.user_id, year)
    if result.is_err:
        return JSONResponse(
            status_code=result.status_code,
            content=ApiResponse.error(result.error).model_dump(),
        )
    return JSONResponse(
        status_code=200,
        content=ApiResponse.ok(data=result.data).model_dump(),
    )
