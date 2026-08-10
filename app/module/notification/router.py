import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.common.dto.pagination import PageQueryDto
from app.common.response import ApiResponse, PaginatedResponse
from app.core.config import settings
from app.module.auth.dependencies import AuthContext, get_auth_context
from app.module.notification.dto.notification import (
    DeviceTokenResponseDto,
    NotificationResponseDto,
    RegisterDeviceTokenDto,
    UnreadCountDto,
)
from app.module.notification.service.device_token_service import (
    DeviceTokenService,
    get_device_token_service,
)
from app.module.notification.service.notification_service import (
    NotificationService,
    get_notification_service,
)
from app.module.notification.service.push_service import PushService, get_push_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=PaginatedResponse[NotificationResponseDto])
async def list_notifications(
    unread_only: bool = Query(False),
    filters: PageQueryDto = Depends(),
    ctx: AuthContext = Depends(get_auth_context),
    service: NotificationService = Depends(get_notification_service),
) -> JSONResponse:
    result = await service.list_for_user(ctx.user_id, filters, unread_only=unread_only)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=result.data.model_dump())


@router.get("/unread-count", response_model=ApiResponse[UnreadCountDto])
async def get_unread_count(
    ctx: AuthContext = Depends(get_auth_context),
    service: NotificationService = Depends(get_notification_service),
) -> JSONResponse:
    result = await service.unread_count(ctx.user_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.put("/read-all", response_model=ApiResponse[None])
async def mark_all_notifications_read(
    ctx: AuthContext = Depends(get_auth_context),
    service: NotificationService = Depends(get_notification_service),
) -> JSONResponse:
    result = await service.mark_all_read(ctx.user_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(message="All notifications marked as read.").model_dump())


@router.put("/{notification_id}/read", response_model=ApiResponse[NotificationResponseDto])
async def mark_notification_read(
    notification_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: NotificationService = Depends(get_notification_service),
) -> JSONResponse:
    result = await service.mark_read(ctx.user_id, notification_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


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


@router.post("/test-push", response_model=ApiResponse[None])
async def send_test_push(
    ctx: AuthContext = Depends(get_auth_context),
    push: PushService = Depends(get_push_service),
) -> JSONResponse:
    """Debug only — sends a plain push to the caller's own registered devices, to confirm registration + FCM are wired up before testing anything feature-specific."""
    if not settings.debug:
        return JSONResponse(status_code=404, content=ApiResponse.error("Not found.").model_dump())

    await push.send_to_user(
        ctx.user_id,
        title="Test notification 🔔",
        body="If you can see this, push notifications are working.",
        data={"type": "test"},
    )
    return JSONResponse(status_code=200, content=ApiResponse.ok(message="Test push sent (if you have a registered device).").model_dump())
