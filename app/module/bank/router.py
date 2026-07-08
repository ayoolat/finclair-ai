import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.common.dto.pagination import PageQueryDto
from app.common.response import ApiResponse, PaginatedResponse
from app.module.auth.dependencies import AuthContext, get_auth_context
from app.module.bank.dto.bank import BankResponseDto, LinkBankDto, MonoWebhookDto
from app.module.bank.service.bank_service import BankService, get_bank_service

router = APIRouter(prefix="/banks", tags=["banks"])


@router.get("", response_model=PaginatedResponse[BankResponseDto])
async def list_banks(
    filters: PageQueryDto = Depends(),
    ctx: AuthContext = Depends(get_auth_context),
    service: BankService = Depends(get_bank_service),
) -> JSONResponse:
    result = await service.list_banks(ctx.user_id, filters)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=result.data.model_dump())


@router.get("/available", response_model=PaginatedResponse[dict])
async def list_available_banks(
    filters: PageQueryDto = Depends(),
    ctx: AuthContext = Depends(get_auth_context),
    service: BankService = Depends(get_bank_service),
) -> JSONResponse:
    result = await service.list_available_banks(filters)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=result.data.model_dump())


@router.post("/link", response_model=ApiResponse[BankResponseDto])
async def link_bank(
    dto: LinkBankDto,
    ctx: AuthContext = Depends(get_auth_context),
    service: BankService = Depends(get_bank_service),
) -> JSONResponse:
    result = await service.link_bank(ctx.user_id, dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=201, content=ApiResponse.ok(data=result.data, message="Bank linked successfully.").model_dump())


@router.post("/{bank_id}/sync", response_model=ApiResponse[dict])
async def sync_transactions(
    bank_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: BankService = Depends(get_bank_service),
) -> JSONResponse:
    result = await service.sync_transactions(ctx.user_id, bank_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data, message="Transactions synced.").model_dump())


@router.delete("/{bank_id}", response_model=ApiResponse[dict])
async def disconnect_bank(
    bank_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: BankService = Depends(get_bank_service),
) -> JSONResponse:
    result = await service.disconnect_bank(ctx.user_id, bank_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.get("/{bank_id}/balance", response_model=ApiResponse[dict])
async def get_balance(
    bank_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: BankService = Depends(get_bank_service),
) -> JSONResponse:
    result = await service.get_balance(ctx.user_id, bank_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.post("/mono/webhook", include_in_schema=False)
async def mono_webhook(
    dto: MonoWebhookDto,
    service: BankService = Depends(get_bank_service),
) -> JSONResponse:
    """Mono webhook receiver — no auth, validated by Mono-Signature header (TODO: add HMAC verification)."""
    return JSONResponse(status_code=200, content={"received": True})
