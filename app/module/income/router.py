import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.common.response import ApiResponse
from app.module.auth.dependencies import AuthContext, get_auth_context
from app.module.income.dto.income import (
    CreateCustomSourceDto,
    CreateIncomeDto,
    IncomeCalculationDto,
    IncomeResponseDto,
    IncomeSourceDto,
    UpdateIncomeAmountDto,
    UpdateIncomeDto,
)
from app.module.income.service.income_service import IncomeService, get_income_service

router = APIRouter(prefix="/income", tags=["income"])


@router.get("/sources", response_model=ApiResponse[list[IncomeSourceDto]])
async def list_sources(
    ctx: AuthContext = Depends(get_auth_context),
    service: IncomeService = Depends(get_income_service),
) -> JSONResponse:
    result = await service.list_sources(ctx.user_id)
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.post("/sources", response_model=ApiResponse[IncomeSourceDto])
async def add_custom_source(
    dto: CreateCustomSourceDto,
    ctx: AuthContext = Depends(get_auth_context),
    service: IncomeService = Depends(get_income_service),
) -> JSONResponse:
    result = await service.add_custom_source(ctx.user_id, dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=result.status_code, content=ApiResponse.ok(data=result.data, message="Source added.").model_dump())


@router.get("/calculate", response_model=ApiResponse[IncomeCalculationDto])
async def calculate_income(
    ctx: AuthContext = Depends(get_auth_context),
    service: IncomeService = Depends(get_income_service),
) -> JSONResponse:
    result = await service.calculate(ctx.user_id)
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.get("", response_model=ApiResponse[IncomeResponseDto])
async def get_income(
    ctx: AuthContext = Depends(get_auth_context),
    service: IncomeService = Depends(get_income_service),
) -> JSONResponse:
    result = await service.get(ctx.user_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.post("", response_model=ApiResponse[IncomeResponseDto])
async def set_income(
    dto: CreateIncomeDto,
    ctx: AuthContext = Depends(get_auth_context),
    service: IncomeService = Depends(get_income_service),
) -> JSONResponse:
    result = await service.upsert(ctx.user_id, dto)
    return JSONResponse(status_code=201, content=ApiResponse.ok(data=result.data, message="Income saved.").model_dump())


@router.patch("", response_model=ApiResponse[IncomeResponseDto])
async def update_income(
    dto: UpdateIncomeDto,
    ctx: AuthContext = Depends(get_auth_context),
    service: IncomeService = Depends(get_income_service),
) -> JSONResponse:
    result = await service.update(ctx.user_id, dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.patch("/{income_id}", response_model=ApiResponse[IncomeResponseDto])
async def update_income_by_id(
    income_id: uuid.UUID,
    dto: UpdateIncomeAmountDto,
    ctx: AuthContext = Depends(get_auth_context),
    service: IncomeService = Depends(get_income_service),
) -> JSONResponse:
    result = await service.update_by_id(ctx.user_id, income_id, dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())
