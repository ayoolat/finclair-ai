import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.common.response import ApiResponse
from app.module.auth.dependencies import AuthContext, get_auth_context
from app.module.notification.dto.notification import DeviceTokenResponseDto, RegisterDeviceTokenDto
from app.module.notification.service.device_token_service import (
    DeviceTokenService,
    get_device_token_service,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post("/device-tokens", response_model=ApiResponse[DeviceTokenResponseDto])
async def register_device_token(
    dto: RegisterDeviceTokenDto,
    ctx: AuthContext = Depends(get_auth_context),
    service: DeviceTokenService = Depends(get_device_token_service),
) -> JSONResponse:
    result = await service.register(ctx.user_id, dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=201, content=ApiResponse.ok(data=result.data, message="Device registered.").model_dump())


@router.get("/device-tokens", response_model=ApiResponse[list[DeviceTokenResponseDto]])
async def list_device_tokens(
    ctx: AuthContext = Depends(get_auth_context),
    service: DeviceTokenService = Depends(get_device_token_service),
) -> JSONResponse:
    result = await service.list_tokens(ctx.user_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.delete("/device-tokens/{token_id}", response_model=ApiResponse[None])
async def unregister_device_token(
    token_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: DeviceTokenService = Depends(get_device_token_service),
) -> JSONResponse:
    result = await service.unregister(ctx.user_id, token_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(message="Device unregistered.").model_dump())
