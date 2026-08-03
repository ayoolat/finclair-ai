import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse
from pydantic import ValidationError

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
    dto: str = Form(
        ...,
        description="JSON-encoded CreateManualExpenseDto. Sent as a form field (not a plain JSON body) so a receipt image can ride along in the same request.",
    ),
    receipt: Optional[UploadFile] = File(
        None, description="Optional receipt image — if provided, the entered amount is AI-verified against it and the expense is marked verified."
    ),
    ctx: AuthContext = Depends(get_auth_context),
    service: ExpenseService = Depends(get_expense_service),
) -> JSONResponse:
    try:
        parsed_dto = CreateManualExpenseDto.model_validate_json(dto)
    except ValidationError as exc:
        errors = [
            {"field": ".".join(str(loc) for loc in error["loc"]), "message": error["msg"], "type": error["type"]}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422, content={"success": False, "message": "Validation failed.", "errors": errors}
        )

    result = await service.create_manual(ctx.user_id, parsed_dto, receipt)
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
    dto: str = Form(
        ...,
        description="JSON-encoded UpdateExpenseDto. Sent as a form field (not a plain JSON body) so a receipt image can ride along in the same request.",
    ),
    receipt: Optional[UploadFile] = File(
        None,
        description="Optional receipt image — if provided, it's AI-verified against dto.amount (or the expense's current amount if amount isn't being changed) and the expense is marked verified.",
    ),
    ctx: AuthContext = Depends(get_auth_context),
    service: ExpenseService = Depends(get_expense_service),
) -> JSONResponse:
    try:
        parsed_dto = UpdateExpenseDto.model_validate_json(dto)
    except ValidationError as exc:
        errors = [
            {"field": ".".join(str(loc) for loc in error["loc"]), "message": error["msg"], "type": error["type"]}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422, content={"success": False, "message": "Validation failed.", "errors": errors}
        )

    result = await service.update(ctx.user_id, expense_id, parsed_dto, receipt)
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
