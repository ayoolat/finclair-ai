import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse

from app.common.response import ApiResponse, PaginatedResponse
from app.module.auth.dependencies import AuthContext, get_auth_context
from app.module.expense.dto.expense import (
    CreateManualExpenseDto,
    ExpenseFilterDto,
    ExpenseResponseDto,
    ExpenseSummaryDto,
    ExpenseSummaryQueryDto,
    UpdateExpenseDto,
)
from app.module.expense.service.expense_service import ExpenseService, get_expense_service

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.get("/summary", response_model=ApiResponse[ExpenseSummaryDto])
async def expense_summary(
    query: ExpenseSummaryQueryDto = Depends(),
    ctx: AuthContext = Depends(get_auth_context),
    service: ExpenseService = Depends(get_expense_service),
) -> JSONResponse:
    result = await service.get_summary(ctx.user_id, query.year, query.month)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.get("", response_model=PaginatedResponse[ExpenseResponseDto])
async def list_expenses(
    filters: ExpenseFilterDto = Depends(),
    ctx: AuthContext = Depends(get_auth_context),
    service: ExpenseService = Depends(get_expense_service),
) -> JSONResponse:
    result = await service.list_expenses(ctx.user_id, filters)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=result.data.model_dump())


@router.get("/{expense_id}", response_model=ApiResponse[ExpenseResponseDto])
async def get_expense(
    expense_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: ExpenseService = Depends(get_expense_service),
) -> JSONResponse:
    result = await service.get(ctx.user_id, expense_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.post("", response_model=ApiResponse[ExpenseResponseDto])
async def create_manual_expense(
    dto: CreateManualExpenseDto,
    ctx: AuthContext = Depends(get_auth_context),
    service: ExpenseService = Depends(get_expense_service),
) -> JSONResponse:
    result = await service.create_manual(ctx.user_id, dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=201, content=ApiResponse.ok(data=result.data, message="Expense recorded.").model_dump())


@router.post("/receipt", response_model=ApiResponse[ExpenseResponseDto])
async def create_receipt_expense(
    image: UploadFile = File(...),
    ctx: AuthContext = Depends(get_auth_context),
    service: ExpenseService = Depends(get_expense_service),
) -> JSONResponse:
    result = await service.create_from_receipt(ctx.user_id, image)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=201, content=ApiResponse.ok(data=result.data, message="Receipt scanned and expense recorded.").model_dump())


@router.patch("/{expense_id}", response_model=ApiResponse[ExpenseResponseDto])
async def update_expense(
    expense_id: uuid.UUID,
    dto: UpdateExpenseDto,
    ctx: AuthContext = Depends(get_auth_context),
    service: ExpenseService = Depends(get_expense_service),
) -> JSONResponse:
    result = await service.update(ctx.user_id, expense_id, dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.delete("/{expense_id}", response_model=ApiResponse[dict])
async def delete_expense(
    expense_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: ExpenseService = Depends(get_expense_service),
) -> JSONResponse:
    result = await service.delete(ctx.user_id, expense_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())
