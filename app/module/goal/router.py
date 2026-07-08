from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.common.dto.pagination import PageQueryDto
from app.common.response import ApiResponse, PaginatedResponse
from app.module.auth.dependencies import AuthContext, get_auth_context
from app.module.goal.dto.goal import FinancialGoalDto
from app.module.goal.service.goal_service import GoalService, get_goal_service

router = APIRouter(prefix="/goals", tags=["goals"])


@router.get("", response_model=PaginatedResponse[FinancialGoalDto])
async def list_goals(
    filters: PageQueryDto = Depends(),
    ctx: AuthContext = Depends(get_auth_context),
    service: GoalService = Depends(get_goal_service),
) -> JSONResponse:
    result = await service.list_goals(filters)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=result.data.model_dump())
