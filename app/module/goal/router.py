from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.common.response import ApiResponse
from app.module.auth.dependencies import AuthContext, get_auth_context
from app.module.goal.dto.goal import FinancialGoalDto
from app.module.goal.service.goal_service import GoalService, get_goal_service

router = APIRouter(prefix="/goals", tags=["goals"])


@router.get("", response_model=ApiResponse[list[FinancialGoalDto]])
async def list_goals(
    ctx: AuthContext = Depends(get_auth_context),
    service: GoalService = Depends(get_goal_service),
) -> JSONResponse:
    result = await service.list_goals()
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())
