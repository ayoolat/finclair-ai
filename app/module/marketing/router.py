from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.common.response import ApiResponse
from app.module.marketing.dto.marketing import NewsletterSubscribeDto, WaitlistJoinDto
from app.module.marketing.service.marketing_service import MarketingService, get_marketing_service

router = APIRouter(prefix="/marketing", tags=["marketing"])


@router.post("/newsletter/subscribe", response_model=ApiResponse[dict])
async def newsletter_subscribe(
    dto: NewsletterSubscribeDto,
    service: MarketingService = Depends(get_marketing_service),
) -> JSONResponse:
    result = await service.newsletter_subscribe(dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    status_code = 201 if result.data.get("subscribed") else 200
    return JSONResponse(
        status_code=status_code,
        content=ApiResponse.ok(data=result.data, message="Subscribed to newsletter.").model_dump(),
    )


@router.post("/waitlist", response_model=ApiResponse[dict])
async def waitlist_join(
    dto: WaitlistJoinDto,
    service: MarketingService = Depends(get_marketing_service),
) -> JSONResponse:
    result = await service.waitlist_join(dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    status_code = 201 if result.data.get("joined") else 200
    return JSONResponse(
        status_code=status_code,
        content=ApiResponse.ok(data=result.data, message="Added to waitlist.").model_dump(),
    )
