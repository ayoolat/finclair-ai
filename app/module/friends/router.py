import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.common.dto.pagination import PageQueryDto
from app.common.response import ApiResponse, PaginatedResponse
from app.module.auth.dependencies import AuthContext, get_auth_context
from app.module.friends.dto.friend import (
    BlockedUserResponseDto,
    FriendshipResponseDto,
    SendInviteDto,
    UserSearchResultDto,
)
from app.module.friends.service.friend_service import FriendService, get_friend_service

router = APIRouter(prefix="/friends", tags=["friends"])


@router.get("/search", response_model=PaginatedResponse[UserSearchResultDto])
async def search_users(
    q: str = Query(..., min_length=1, max_length=50),
    filters: PageQueryDto = Depends(),
    ctx: AuthContext = Depends(get_auth_context),
    service: FriendService = Depends(get_friend_service),
) -> JSONResponse:
    result = await service.search_users(q, ctx.user_id, filters)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=result.data.model_dump())


@router.get("", response_model=PaginatedResponse[FriendshipResponseDto])
async def list_friends(
    filters: PageQueryDto = Depends(),
    ctx: AuthContext = Depends(get_auth_context),
    service: FriendService = Depends(get_friend_service),
) -> JSONResponse:
    result = await service.list_friends(ctx.user_id, filters)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=result.data.model_dump())


@router.post("/invite", response_model=ApiResponse[FriendshipResponseDto])
async def send_invite(
    dto: SendInviteDto,
    ctx: AuthContext = Depends(get_auth_context),
    service: FriendService = Depends(get_friend_service),
) -> JSONResponse:
    result = await service.send_invite(ctx.user_id, dto.recipient_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=201, content=ApiResponse.ok(data=result.data, message="Invite sent.").model_dump())


@router.get("/invites", response_model=PaginatedResponse[FriendshipResponseDto])
async def list_invites(
    filters: PageQueryDto = Depends(),
    ctx: AuthContext = Depends(get_auth_context),
    service: FriendService = Depends(get_friend_service),
) -> JSONResponse:
    result = await service.list_invites(ctx.user_id, filters)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=result.data.model_dump())


@router.put("/invites/{invite_id}/accept", response_model=ApiResponse[FriendshipResponseDto])
async def accept_invite(
    invite_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: FriendService = Depends(get_friend_service),
) -> JSONResponse:
    result = await service.accept_invite(ctx.user_id, invite_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data, message="Invite accepted.").model_dump())


@router.put("/invites/{invite_id}/decline", response_model=ApiResponse[FriendshipResponseDto])
async def decline_invite(
    invite_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: FriendService = Depends(get_friend_service),
) -> JSONResponse:
    result = await service.decline_invite(ctx.user_id, invite_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(data=result.data, message="Invite declined.").model_dump())


@router.delete("/{friendship_id}", response_model=ApiResponse[None])
async def remove_friend(
    friendship_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: FriendService = Depends(get_friend_service),
) -> JSONResponse:
    result = await service.remove_friend(ctx.user_id, friendship_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(message="Friend removed.").model_dump())


@router.get("/blocked", response_model=PaginatedResponse[BlockedUserResponseDto])
async def list_blocked_users(
    filters: PageQueryDto = Depends(),
    ctx: AuthContext = Depends(get_auth_context),
    service: FriendService = Depends(get_friend_service),
) -> JSONResponse:
    result = await service.list_blocked_users(ctx.user_id, filters)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=result.data.model_dump())


@router.post("/block/{user_id}", response_model=ApiResponse[None])
async def block_user(
    user_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: FriendService = Depends(get_friend_service),
) -> JSONResponse:
    result = await service.block_user(ctx.user_id, user_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(message="User blocked.").model_dump())


@router.delete("/block/{user_id}", response_model=ApiResponse[None])
async def unblock_user(
    user_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    service: FriendService = Depends(get_friend_service),
) -> JSONResponse:
    result = await service.unblock_user(ctx.user_id, user_id)
    if result.is_err:
        return JSONResponse(status_code=result.status_code, content=ApiResponse.error(result.error).model_dump())
    return JSONResponse(status_code=200, content=ApiResponse.ok(message="User unblocked.").model_dump())
