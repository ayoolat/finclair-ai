from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.common.response import ApiResponse
from app.module.auth.dependencies import AuthContext, get_auth_context
from app.module.insight.dto.insight import HomeInsightDto
from app.module.insight.service.insight_service import InsightService, get_insight_service

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/home", response_model=ApiResponse[HomeInsightDto])
async def home_insight(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    ctx: AuthContext = Depends(get_auth_context),
    service: InsightService = Depends(get_insight_service),
) -> JSONResponse:
    result = await service.home_insight(ctx.user_id, start_date, end_date)
    if result.is_err:
        return JSONResponse(
            status_code=result.status_code,
            content=ApiResponse.error(result.error).model_dump(),
        )
    return JSONResponse(
        status_code=200,
        content=ApiResponse.ok(data=result.data).model_dump(),
    )
