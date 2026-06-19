import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.common.response import ApiResponse
from app.module.auth.dependencies import AuthContext, get_auth_context
from app.module.budget.dto.budget import (
    BudgetResponseDto,
    CreateBudgetDto,
    UpdateBudgetDto,
    UpsertAllocationDto,
)
from app.module.budget.service.budget_service import BudgetService, get_budget_service

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.get("", response_model=ApiResponse[list[BudgetResponseDto]])
async def list_budgets(
    ctx: AuthContext = Depends(get_auth_context),
    service: BudgetService = Depends(get_budget_service),
) -> JSONResponse:
    result = await service.list_budgets(ctx.user_id)
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.get("/{budget_id}", response_model=ApiResponse[BudgetResponseDto])
async def get_budget(
    budget_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: BudgetService = Depends(get_budget_service),
) -> JSONResponse:
    result = await service.get(ctx.user_id, budget_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.post("", response_model=ApiResponse[BudgetResponseDto])
async def create_budget(
    dto: CreateBudgetDto,
    ctx: AuthContext = Depends(get_auth_context),
    service: BudgetService = Depends(get_budget_service),
) -> JSONResponse:
    result = await service.create(ctx.user_id, dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=201, content=ApiResponse.ok(data=result.data, message="Budget created.").model_dump())


@router.patch("/{budget_id}", response_model=ApiResponse[BudgetResponseDto])
async def update_budget(
    budget_id: uuid.UUID,
    dto: UpdateBudgetDto,
    ctx: AuthContext = Depends(get_auth_context),
    service: BudgetService = Depends(get_budget_service),
) -> JSONResponse:
    result = await service.update(ctx.user_id, budget_id, dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.delete("/{budget_id}", response_model=ApiResponse[dict])
async def delete_budget(
    budget_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: BudgetService = Depends(get_budget_service),
) -> JSONResponse:
    result = await service.delete(ctx.user_id, budget_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.put("/{budget_id}/allocations", response_model=ApiResponse[BudgetResponseDto])
async def upsert_allocation(
    budget_id: uuid.UUID,
    dto: UpsertAllocationDto,
    ctx: AuthContext = Depends(get_auth_context),
    service: BudgetService = Depends(get_budget_service),
) -> JSONResponse:
    result = await service.upsert_allocation(ctx.user_id, budget_id, dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.delete("/{budget_id}/allocations/{category_id}", response_model=ApiResponse[BudgetResponseDto])
async def delete_allocation(
    budget_id: uuid.UUID,
    category_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: BudgetService = Depends(get_budget_service),
) -> JSONResponse:
    result = await service.delete_allocation(ctx.user_id, budget_id, category_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())
