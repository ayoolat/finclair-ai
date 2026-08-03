import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse

from app.common.dto.pagination import PageQueryDto
from app.common.response import ApiResponse, PaginatedResponse
from app.module.auth.dependencies import AuthContext, get_auth_context
from app.module.challenge.dto.challenge import (
    BadgeResponseDto,
    ChallengeEntryResponseDto,
    ChallengeFilterDto,
    ChallengeResponseDto,
    CreateChallengeDto,
    RecordEntryDto,
    UpdateChallengeDto,
    UserBadgeResponseDto,
)
from app.module.challenge.service.badge_service import BadgeService, get_badge_service
from app.module.challenge.service.challenge_entry_service import (
    ChallengeEntryService,
    get_challenge_entry_service,
)
from app.module.challenge.service.challenge_service import ChallengeService, get_challenge_service

router = APIRouter(prefix="/challenges", tags=["challenges"])


# ── Badges (static paths — declared before /{challenge_id} to avoid shadowing) ─

@router.get("/badges/catalog", response_model=ApiResponse[list[BadgeResponseDto]])
async def list_badge_catalog(
    service: BadgeService = Depends(get_badge_service),
) -> JSONResponse:
    result = await service.list_catalog()
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.get("/badges/mine", response_model=ApiResponse[list[UserBadgeResponseDto]])
async def list_my_badges(
    ctx: AuthContext = Depends(get_auth_context),
    service: BadgeService = Depends(get_badge_service),
) -> JSONResponse:
    result = await service.list_user_badges(ctx.user_id)
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


# ── Challenge CRUD ────────────────────────────────────────────────────────────

@router.post("", response_model=ApiResponse[ChallengeResponseDto])
async def create_challenge(
    dto: CreateChallengeDto,
    ctx: AuthContext = Depends(get_auth_context),
    service: ChallengeService = Depends(get_challenge_service),
) -> JSONResponse:
    result = await service.create_challenge(ctx.user_id, dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=201, content=ApiResponse.ok(data=result.data, message="Challenge created.").model_dump())


@router.get("", response_model=PaginatedResponse[ChallengeResponseDto])
async def list_challenges(
    filters: ChallengeFilterDto = Depends(),
    ctx: AuthContext = Depends(get_auth_context),
    service: ChallengeService = Depends(get_challenge_service),
) -> JSONResponse:
    result = await service.list_challenges(ctx.user_id, filters)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=result.data.model_dump())


@router.get("/{challenge_id}", response_model=ApiResponse[ChallengeResponseDto])
async def get_challenge(
    challenge_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: ChallengeService = Depends(get_challenge_service),
) -> JSONResponse:
    result = await service.get_challenge(ctx.user_id, challenge_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.put("/{challenge_id}", response_model=ApiResponse[ChallengeResponseDto])
async def update_challenge(
    challenge_id: uuid.UUID,
    dto: UpdateChallengeDto,
    ctx: AuthContext = Depends(get_auth_context),
    service: ChallengeService = Depends(get_challenge_service),
) -> JSONResponse:
    result = await service.update_challenge(ctx.user_id, challenge_id, dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data, message="Challenge updated.").model_dump())


@router.delete("/{challenge_id}", response_model=ApiResponse[None])
async def cancel_challenge(
    challenge_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: ChallengeService = Depends(get_challenge_service),
) -> JSONResponse:
    result = await service.cancel_challenge(ctx.user_id, challenge_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(message="Challenge cancelled.").model_dump())


# ── Entries ───────────────────────────────────────────────────────────────────

@router.post("/{challenge_id}/entries", response_model=ApiResponse[ChallengeEntryResponseDto])
async def record_entry(
    challenge_id: uuid.UUID,
    amount: Optional[Decimal] = Form(None),
    note: Optional[str] = Form(None),
    receipt: Optional[UploadFile] = File(None),
    ctx: AuthContext = Depends(get_auth_context),
    service: ChallengeEntryService = Depends(get_challenge_entry_service),
) -> JSONResponse:
    result = await service.record_entry(
        ctx.user_id, challenge_id, RecordEntryDto(amount=amount, note=note), receipt
    )
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=201, content=ApiResponse.ok(data=result.data, message="Savings logged.").model_dump())


@router.get("/{challenge_id}/entries", response_model=PaginatedResponse[ChallengeEntryResponseDto])
async def list_entries(
    challenge_id: uuid.UUID,
    filters: PageQueryDto = Depends(),
    ctx: AuthContext = Depends(get_auth_context),
    service: ChallengeEntryService = Depends(get_challenge_entry_service),
) -> JSONResponse:
    result = await service.list_entries(ctx.user_id, challenge_id, filters)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=result.data.model_dump())


# ── Test helpers (settings.debug only — 404s otherwise) ────────────────────────
# For testers: see the streak/reminder push notifications without waiting for
# real Fridays or weeks of real usage.

@router.post("/{challenge_id}/dev/simulate-streak", response_model=ApiResponse[ChallengeResponseDto])
async def simulate_streak(
    challenge_id: uuid.UUID,
    weeks: int = Query(..., ge=1, le=52, description="Jump the streak to this many weeks and fire the same badge/push logic as a real entry."),
    ctx: AuthContext = Depends(get_auth_context),
    service: ChallengeEntryService = Depends(get_challenge_entry_service),
) -> JSONResponse:
    result = await service.simulate_streak(ctx.user_id, challenge_id, weeks)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data, message="Streak simulated.").model_dump())


@router.post("/{challenge_id}/dev/send-test-reminder", response_model=ApiResponse[None])
async def send_test_reminder(
    challenge_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: ChallengeEntryService = Depends(get_challenge_entry_service),
) -> JSONResponse:
    result = await service.send_test_reminder(ctx.user_id, challenge_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(message="Test reminder sent.").model_dump())
