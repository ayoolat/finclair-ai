import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from jose import JWTError

from app.common.dto.pagination import PageQueryDto
from app.common.enums.groups import RedistributionChoice
from app.common.response import ApiResponse, PaginatedResponse
from app.common.security.token import decode_token
from app.database.session import AsyncSessionLocal
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
from app.module.groups.ws.connection_manager import ws_manager

router = APIRouter(prefix="/groups", tags=["groups"])


# ── Group CRUD ────────────────────────────────────────────────────────────────

@router.get("", response_model=PaginatedResponse[GroupResponseDto])
async def list_groups(
    filters: PageQueryDto = Depends(),
    ctx: AuthContext = Depends(get_auth_context),
    service: GroupService = Depends(get_group_service),
) -> JSONResponse:
    result = await service.list_groups(ctx.user_id, filters)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=result.data.model_dump())


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
    redistribution: RedistributionChoice = Query(
        ..., description="What to do with the removed member's unmet target: 'self' assigns it to you, 'split' divides it equally among the remaining members."
    ),
    ctx: AuthContext = Depends(get_auth_context),
    service: GroupMemberService = Depends(get_group_member_service),
) -> JSONResponse:
    result = await service.remove_member(ctx.user_id, group_id, member_id, redistribution)
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


@router.get("/{group_id}/savings", response_model=PaginatedResponse[SavingsEntryResponseDto])
async def list_savings(
    group_id: uuid.UUID,
    filters: PageQueryDto = Depends(),
    ctx: AuthContext = Depends(get_auth_context),
    service: GroupSavingsService = Depends(get_group_savings_service),
) -> JSONResponse:
    result = await service.list_savings(ctx.user_id, group_id, filters)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=result.data.model_dump())


# ── Chat ──────────────────────────────────────────────────────────────────────

@router.get("/{group_id}/messages", response_model=PaginatedResponse[MessageResponseDto])
async def list_messages(
    group_id: uuid.UUID,
    filters: PageQueryDto = Depends(),
    ctx: AuthContext = Depends(get_auth_context),
    service: GroupChatService = Depends(get_group_chat_service),
) -> JSONResponse:
    result = await service.list_messages(ctx.user_id, group_id, filters)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=result.data.model_dump())


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
    await ws_manager.broadcast(group_id, {
        "type": "message",
        "data": result.data.model_dump(mode="json"),
    })
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
    await ws_manager.broadcast(group_id, {
        "type": "message",
        "data": result.data.model_dump(mode="json"),
    })
    return JSONResponse(status_code=201, content=ApiResponse.ok(data=result.data).model_dump())


# ── WebSocket Chat ────────────────────────────────────────────────────────────

@router.websocket("/{group_id}/ws")
async def group_chat_ws(
    group_id: uuid.UUID,
    websocket: WebSocket,
    token: str = Query(default=""),
) -> None:
    # Authenticate via token query param (WS upgrade doesn't support Authorization header)
    try:
        user_id, _ = decode_token(token)
    except (JWTError, ValueError, KeyError):
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # Verify group membership before accepting the connection
    async with AsyncSessionLocal() as db:
        svc = GroupChatService(db)
        if not await svc._is_member(user_id, group_id):
            await websocket.close(code=4003, reason="Not a group member")
            return

    await ws_manager.connect(group_id, user_id, websocket)
    await websocket.send_json({"type": "connected", "group_id": str(group_id)})

    try:
        while True:
            data = await websocket.receive_json()
            content = (data.get("content") or "").strip()
            if not content:
                continue

            async with AsyncSessionLocal() as db:
                svc = GroupChatService(db)
                result = await svc.send_text(user_id, group_id, SendMessageDto(content=content))

            if result.is_err:
                await websocket.send_json({"type": "error", "message": result.error})
                continue

            await ws_manager.broadcast(group_id, {
                "type": "message",
                "data": result.data.model_dump(mode="json"),
            })

    except WebSocketDisconnect:
        ws_manager.disconnect(group_id, user_id)
