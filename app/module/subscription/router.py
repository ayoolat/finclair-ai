from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.common.response import ApiResponse
from app.module.auth.dependencies import AuthContext, get_auth_context
from app.module.subscription.dto.subscription import PlansResponseDto, SubscriptionDto, VerifyCheckoutDto
from app.module.subscription.service.subscription_service import SubscriptionService, get_subscription_service

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.get("/plans", response_model=ApiResponse[PlansResponseDto])
async def list_plans(
    ctx: AuthContext = Depends(get_auth_context),
    service: SubscriptionService = Depends(get_subscription_service),
) -> JSONResponse:
    result = await service.get_plans()
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(result.data).model_dump())


@router.get("/me", response_model=ApiResponse[SubscriptionDto])
async def get_my_subscription(
    ctx: AuthContext = Depends(get_auth_context),
    service: SubscriptionService = Depends(get_subscription_service),
) -> JSONResponse:
    result = await service.get_my_subscription(ctx.user_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(result.data).model_dump())


@router.post("/checkout/verify", response_model=ApiResponse[SubscriptionDto])
async def verify_checkout(
    dto: VerifyCheckoutDto,
    ctx: AuthContext = Depends(get_auth_context),
    service: SubscriptionService = Depends(get_subscription_service),
) -> JSONResponse:
    result = await service.verify_checkout(ctx.user_id, dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(result.data).model_dump())


@router.post("/cancel", response_model=ApiResponse[SubscriptionDto])
async def cancel_subscription(
    ctx: AuthContext = Depends(get_auth_context),
    service: SubscriptionService = Depends(get_subscription_service),
) -> JSONResponse:
    result = await service.cancel(ctx.user_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(result.data).model_dump())


@router.post("/resume", response_model=ApiResponse[SubscriptionDto])
async def resume_subscription(
    ctx: AuthContext = Depends(get_auth_context),
    service: SubscriptionService = Depends(get_subscription_service),
) -> JSONResponse:
    result = await service.resume(ctx.user_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(result.data).model_dump())
