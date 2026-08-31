from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.common.response import ApiResponse
from app.module.auth.dependencies import AuthContext, get_auth_context
from app.module.score.dto.score import FinclarScoreDto
from app.module.score.service.score_service import ScoreService, get_score_service

router = APIRouter(prefix="/score", tags=["score"])


@router.get("", response_model=ApiResponse[FinclarScoreDto])
async def get_finclar_score(
    year: Optional[int] = Query(None, description="Calendar year to score. Defaults to the current year."),
    month: Optional[int] = Query(None, ge=1, le=12, description="Calendar month (1-12) to score. Defaults to the current month."),
    ctx: AuthContext = Depends(get_auth_context),
    service: ScoreService = Depends(get_score_service),
) -> JSONResponse:
    result = await service.get_score(ctx.user_id, year, month)
    if result.is_err:
        return JSONResponse(
            status_code=result.status_code,
            content=ApiResponse.error(result.error).model_dump(),
        )
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())
