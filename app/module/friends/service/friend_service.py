import uuid

from fastapi import Depends
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.dto.pagination import PageQueryDto
from app.common.enums.friends import FriendshipStatus
from app.common.enums.notification import NotificationType
from app.common.response import PaginatedResponse, Result
from app.database.session import get_db
from app.module.friends.dto.friend import BlockedUserResponseDto, FriendshipResponseDto, UserSearchResultDto
from app.module.friends.schema.friendship import Friendship
from app.module.friends.schema.user_block import UserBlock
from app.module.notification.service.notification_service import NotificationService, get_notification_service
from app.module.user.schema.user import User


class FriendService:
    def __init__(self, db: AsyncSession, notifications: NotificationService) -> None:
        self._db = db
        self._notifications = notifications

    async def search_users(
        self, query: str, current_user_id: uuid.UUID, filters: PageQueryDto
    ) -> Result[PaginatedResponse[UserSearchResultDto]]:
        blocked_by_candidate = self._blocked_by_clause(current_user_id, User.id)
        base = select(User).where(
            User.username.ilike(query),
            User.id != current_user_id,
            User.is_active.is_(True),
            ~blocked_by_candidate,
        )
        total = (await self._db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

        result = await self._db.execute(base.offset(filters.offset).limit(filters.page_size))
        users = result.scalars().all()
        dtos = [UserSearchResultDto.model_validate(u) for u in users]
        return Result.ok(PaginatedResponse.ok(data=dtos, page=filters.page, page_size=filters.page_size, total=total))

    async def send_invite(self, requester_id: uuid.UUID, recipient_id: uuid.UUID) -> Result[FriendshipResponseDto]:
        if requester_id == recipient_id:
            return Result.fail("Cannot send invite to yourself.")

        user_result = await self._db.execute(select(User).where(User.id == recipient_id))
        if not user_result.scalar_one_or_none():
            return Result.fail("User not found.", status_code=404)

        block_result = await self._db.execute(
            select(UserBlock).where(
                or_(
                    and_(UserBlock.blocker_id == requester_id, UserBlock.blocked_id == recipient_id),
                    and_(UserBlock.blocker_id == recipient_id, UserBlock.blocked_id == requester_id),
                )
            )
        )
        if block_result.scalar_one_or_none():
            return Result.fail("Cannot send invite to this user.", status_code=403)

        existing = await self._db.execute(
            select(Friendship).where(
                or_(
                    and_(Friendship.requester_id == requester_id, Friendship.recipient_id == recipient_id),
                    and_(Friendship.requester_id == recipient_id, Friendship.recipient_id == requester_id),
                )
            )
        )
        if existing.scalar_one_or_none():
            return Result.fail("A friendship or pending invite already exists.")

        friendship = Friendship(
            requester_id=requester_id,
            recipient_id=recipient_id,
            status=FriendshipStatus.PENDING,
        )
        self._db.add(friendship)
        await self._db.commit()

        loaded = await self._db.execute(
            select(Friendship)
            .options(selectinload(Friendship.requester), selectinload(Friendship.recipient))
            .where(Friendship.id == friendship.id)
        )
        friendship = loaded.scalar_one()

        await self._notifications.notify(
            recipient_id,
            NotificationType.FRIEND_INVITE,
            title="New friend request",
            body=f"{friendship.requester.display_name} wants to be friends.",
            data={"friendship_id": str(friendship.id), "requester_id": str(requester_id)},
        )

        return Result.ok(self._to_dto(friendship, requester_id), status_code=201)

    async def list_invites(
        self, user_id: uuid.UUID, filters: PageQueryDto
    ) -> Result[PaginatedResponse[FriendshipResponseDto]]:
        base = select(Friendship).where(
            Friendship.recipient_id == user_id,
            Friendship.status == FriendshipStatus.PENDING,
        )
        total = (await self._db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

        result = await self._db.execute(
            base.options(selectinload(Friendship.requester), selectinload(Friendship.recipient))
            .offset(filters.offset)
            .limit(filters.page_size)
        )
        friendships = result.scalars().all()
        dtos = [self._to_dto(f, user_id) for f in friendships]
        return Result.ok(PaginatedResponse.ok(data=dtos, page=filters.page, page_size=filters.page_size, total=total))

    async def accept_invite(self, user_id: uuid.UUID, invite_id: uuid.UUID) -> Result[FriendshipResponseDto]:
        return await self._update_invite_status(user_id, invite_id, FriendshipStatus.ACCEPTED)

    async def decline_invite(self, user_id: uuid.UUID, invite_id: uuid.UUID) -> Result[FriendshipResponseDto]:
        return await self._update_invite_status(user_id, invite_id, FriendshipStatus.DECLINED)

    async def list_friends(
        self, user_id: uuid.UUID, filters: PageQueryDto
    ) -> Result[PaginatedResponse[FriendshipResponseDto]]:
        base = select(Friendship).where(
            or_(Friendship.requester_id == user_id, Friendship.recipient_id == user_id),
            Friendship.status == FriendshipStatus.ACCEPTED,
        )
        total = (await self._db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

        result = await self._db.execute(
            base.options(selectinload(Friendship.requester), selectinload(Friendship.recipient))
            .offset(filters.offset)
            .limit(filters.page_size)
        )
        friendships = result.scalars().all()
        dtos = [self._to_dto(f, user_id) for f in friendships]
        return Result.ok(PaginatedResponse.ok(data=dtos, page=filters.page, page_size=filters.page_size, total=total))

    async def remove_friend(self, user_id: uuid.UUID, friendship_id: uuid.UUID) -> Result[None]:
        result = await self._db.execute(
            select(Friendship).where(
                Friendship.id == friendship_id,
                or_(Friendship.requester_id == user_id, Friendship.recipient_id == user_id),
                Friendship.status == FriendshipStatus.ACCEPTED,
            )
        )
        friendship = result.scalar_one_or_none()
        if not friendship:
            return Result.fail("Friendship not found.", status_code=404)
        await self._db.delete(friendship)
        await self._db.commit()
        return Result.ok(None)

    async def block_user(self, user_id: uuid.UUID, target_id: uuid.UUID) -> Result[None]:
        if user_id == target_id:
            return Result.fail("Cannot block yourself.")

        user_result = await self._db.execute(select(User).where(User.id == target_id))
        if not user_result.scalar_one_or_none():
            return Result.fail("User not found.", status_code=404)

        existing = await self._db.execute(
            select(UserBlock).where(UserBlock.blocker_id == user_id, UserBlock.blocked_id == target_id)
        )
        if existing.scalar_one_or_none():
            return Result.fail("User is already blocked.")

        friendship_result = await self._db.execute(
            select(Friendship).where(
                or_(
                    and_(Friendship.requester_id == user_id, Friendship.recipient_id == target_id),
                    and_(Friendship.requester_id == target_id, Friendship.recipient_id == user_id),
                )
            )
        )
        for friendship in friendship_result.scalars().all():
            await self._db.delete(friendship)

        self._db.add(UserBlock(blocker_id=user_id, blocked_id=target_id))
        await self._db.commit()
        return Result.ok(None)

    async def unblock_user(self, user_id: uuid.UUID, target_id: uuid.UUID) -> Result[None]:
        result = await self._db.execute(
            select(UserBlock).where(UserBlock.blocker_id == user_id, UserBlock.blocked_id == target_id)
        )
        block = result.scalar_one_or_none()
        if not block:
            return Result.fail("Block not found.", status_code=404)
        await self._db.delete(block)
        await self._db.commit()
        return Result.ok(None)

    async def list_blocked_users(
        self, user_id: uuid.UUID, filters: PageQueryDto
    ) -> Result[PaginatedResponse[BlockedUserResponseDto]]:
        base = select(UserBlock).where(UserBlock.blocker_id == user_id)
        total = (await self._db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

        result = await self._db.execute(
            base.options(selectinload(UserBlock.blocked)).offset(filters.offset).limit(filters.page_size)
        )
        blocks = result.scalars().all()
        dtos = [
            BlockedUserResponseDto(
                id=b.id,
                user_id=b.blocked_id,
                username=b.blocked.username,
                email=b.blocked.email,
                profile_icon=b.blocked.profile_icon,
                blocked_at=b.created_at,
            )
            for b in blocks
        ]
        return Result.ok(PaginatedResponse.ok(data=dtos, page=filters.page, page_size=filters.page_size, total=total))

    @staticmethod
    def _blocked_by_clause(user_id: uuid.UUID, other_user_col):
        # Only hides candidates who blocked `user_id` — a blocker keeps seeing
        # who they blocked (needed to unblock them), the blocked side does not.
        return (
            select(UserBlock.id)
            .where(UserBlock.blocker_id == other_user_col, UserBlock.blocked_id == user_id)
            .exists()
        )

    async def _update_invite_status(
        self, user_id: uuid.UUID, invite_id: uuid.UUID, status: FriendshipStatus
    ) -> Result[FriendshipResponseDto]:
        result = await self._db.execute(
            select(Friendship)
            .options(selectinload(Friendship.requester), selectinload(Friendship.recipient))
            .where(
                Friendship.id == invite_id,
                Friendship.recipient_id == user_id,
                Friendship.status == FriendshipStatus.PENDING,
            )
        )
        friendship = result.scalar_one_or_none()
        if not friendship:
            return Result.fail("Invite not found.", status_code=404)
        friendship.status = status
        await self._db.commit()
        return Result.ok(self._to_dto(friendship, user_id))

    def _to_dto(self, f: Friendship, current_user_id: uuid.UUID) -> FriendshipResponseDto:
        is_requester = f.requester_id == current_user_id
        friend = f.recipient if is_requester else f.requester
        friend_id = f.recipient_id if is_requester else f.requester_id
        return FriendshipResponseDto(
            id=f.id,
            requester_id=f.requester_id,
            recipient_id=f.recipient_id,
            status=FriendshipStatus(f.status),
            created_at=f.created_at,
            friend_id=friend_id,
            friend_username=friend.username if friend else "",
            friend_email=friend.email if friend else "",
            friend_profile_icon=friend.profile_icon if friend else None,
        )


def get_friend_service(
    db: AsyncSession = Depends(get_db),
    notifications: NotificationService = Depends(get_notification_service),
) -> FriendService:
    return FriendService(db, notifications)
