import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse

from app.common.response import ApiResponse
from app.module.auth.dependencies import AuthContext, get_auth_context
from app.module.groups.dto.group import (
    CreateGroupDto,
    GroupDetailResponseDto,
    GroupMemberResponseDto,
    GroupResponseDto,
    MessageResponseDto,
    RecordSavingsDto,
    SavingsEntryResponseDto,
    SendMessageDto,
    UpdateGroupDto,
    UpdateMemberDto,
)
from app.module.groups.service.group_chat_service import GroupChatService, get_group_chat_service
from app.module.groups.service.group_member_service import GroupMemberService, get_group_member_service
from app.module.groups.service.group_savings_service import GroupSavingsService, get_group_savings_service
from app.module.groups.service.group_service import GroupService, get_group_service

router = APIRouter(prefix="/groups", tags=["groups"])


# ── Group CRUD ────────────────────────────────────────────────────────────────

@router.get("", response_model=ApiResponse[list[GroupResponseDto]])
async def list_groups(
    ctx: AuthContext = Depends(get_auth_context),
    service: GroupService = Depends(get_group_service),
) -> JSONResponse:
    result = await service.list_groups(ctx.user_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.post("", response_model=ApiResponse[GroupDetailResponseDto])
async def create_group(
    dto: CreateGroupDto,
    ctx: AuthContext = Depends(get_auth_context),
    service: GroupService = Depends(get_group_service),
) -> JSONResponse:
    result = await service.create_group(ctx.user_id, dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=201, content=ApiResponse.ok(data=result.data, message="Group created.").model_dump())


@router.get("/{group_id}", response_model=ApiResponse[GroupDetailResponseDto])
async def get_group(
    group_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: GroupService = Depends(get_group_service),
) -> JSONResponse:
    result = await service.get_group(ctx.user_id, group_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.put("/{group_id}", response_model=ApiResponse[GroupResponseDto])
async def update_group(
    group_id: uuid.UUID,
    dto: UpdateGroupDto,
    ctx: AuthContext = Depends(get_auth_context),
    service: GroupService = Depends(get_group_service),
) -> JSONResponse:
    result = await service.update_group(ctx.user_id, group_id, dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data, message="Group updated.").model_dump())


@router.delete("/{group_id}", response_model=ApiResponse[None])
async def delete_group(
    group_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: GroupService = Depends(get_group_service),
) -> JSONResponse:
    result = await service.delete_group(ctx.user_id, group_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(message="Group deleted.").model_dump())


@router.post("/{group_id}/leave", response_model=ApiResponse[None])
async def leave_group(
    group_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: GroupService = Depends(get_group_service),
) -> JSONResponse:
    result = await service.leave_group(ctx.user_id, group_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(message="You have left the group.").model_dump())


@router.get("/{group_id}/share", response_model=ApiResponse[dict])
async def get_share_link(
    group_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: GroupService = Depends(get_group_service),
) -> JSONResponse:
    result = await service.get_share_link(ctx.user_id, group_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


# ── Members ───────────────────────────────────────────────────────────────────

@router.put("/{group_id}/members/{member_id}", response_model=ApiResponse[GroupMemberResponseDto])
async def update_member(
    group_id: uuid.UUID,
    member_id: uuid.UUID,
    dto: UpdateMemberDto,
    ctx: AuthContext = Depends(get_auth_context),
    service: GroupMemberService = Depends(get_group_member_service),
) -> JSONResponse:
    result = await service.update_member(ctx.user_id, group_id, member_id, dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data, message="Member updated.").model_dump())


@router.delete("/{group_id}/members/{member_id}", response_model=ApiResponse[None])
async def remove_member(
    group_id: uuid.UUID,
    member_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: GroupMemberService = Depends(get_group_member_service),
) -> JSONResponse:
    result = await service.remove_member(ctx.user_id, group_id, member_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(message="Member removed.").model_dump())


# ── Savings ───────────────────────────────────────────────────────────────────

@router.post("/{group_id}/savings", response_model=ApiResponse[SavingsEntryResponseDto])
async def record_savings(
    group_id: uuid.UUID,
    amount: Decimal = Form(...),
    note: Optional[str] = Form(None),
    receipt: Optional[UploadFile] = File(None),
    ctx: AuthContext = Depends(get_auth_context),
    service: GroupSavingsService = Depends(get_group_savings_service),
) -> JSONResponse:
    result = await service.record_savings(ctx.user_id, group_id, RecordSavingsDto(amount=amount, note=note), receipt)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=201, content=ApiResponse.ok(data=result.data, message="Savings recorded.").model_dump())


@router.get("/{group_id}/savings", response_model=ApiResponse[list[SavingsEntryResponseDto]])
async def list_savings(
    group_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: GroupSavingsService = Depends(get_group_savings_service),
) -> JSONResponse:
    result = await service.list_savings(ctx.user_id, group_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


# ── Chat ──────────────────────────────────────────────────────────────────────

@router.get("/{group_id}/messages", response_model=ApiResponse[list[MessageResponseDto]])
async def list_messages(
    group_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    ctx: AuthContext = Depends(get_auth_context),
    service: GroupChatService = Depends(get_group_chat_service),
) -> JSONResponse:
    result = await service.list_messages(ctx.user_id, group_id, page, limit)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data).model_dump())


@router.post("/{group_id}/messages", response_model=ApiResponse[MessageResponseDto])
async def send_message(
    group_id: uuid.UUID,
    dto: SendMessageDto,
    ctx: AuthContext = Depends(get_auth_context),
    service: GroupChatService = Depends(get_group_chat_service),
) -> JSONResponse:
    result = await service.send_text(ctx.user_id, group_id, dto)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=201, content=ApiResponse.ok(data=result.data).model_dump())


@router.post("/{group_id}/messages/attachment", response_model=ApiResponse[MessageResponseDto])
async def send_attachment(
    group_id: uuid.UUID,
    file: UploadFile = File(...),
    record_amount: Optional[Decimal] = Form(None),
    ctx: AuthContext = Depends(get_auth_context),
    service: GroupChatService = Depends(get_group_chat_service),
) -> JSONResponse:
    result = await service.send_attachment(ctx.user_id, group_id, file, record_amount)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=201, content=ApiResponse.ok(data=result.data).model_dump())
