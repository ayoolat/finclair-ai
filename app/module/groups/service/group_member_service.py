import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from fastapi import Depends
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums.friends import FriendshipStatus
from app.common.enums.groups import GroupInviteStatus, GroupMemberStatus, InviteResponse, RedistributionChoice
from app.common.response import Result
from app.database.session import get_db
from app.module.friends.schema.friendship import Friendship
from app.module.groups.dto.group import AddMemberDto, GroupMemberResponseDto, UpdateMemberDto
from app.module.groups.schema.group import Group
from app.module.groups.schema.group_member import GroupMember
from app.module.groups.service._helpers import member_to_dto
from app.module.groups.service.group_service import FREE_MEMBER_LIMIT
from app.module.user.schema.user import User


class GroupMemberService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add_member(
        self, owner_id: uuid.UUID, group_id: uuid.UUID, dto: AddMemberDto
    ) -> Result[GroupMemberResponseDto]:
        if not await self._is_owner(owner_id, group_id):
            return Result.fail("Group not found or you are not the owner.", status_code=404)

        if dto.user_id == owner_id:
            return Result.fail("You are already in this group.", status_code=409)

        target_user = await self._db.scalar(select(User).where(User.id == dto.user_id))
        if target_user is None:
            return Result.fail("User not found.", status_code=404)

        is_friend = await self._db.scalar(
            select(Friendship).where(
                or_(
                    and_(Friendship.requester_id == owner_id, Friendship.recipient_id == dto.user_id),
                    and_(Friendship.requester_id == dto.user_id, Friendship.recipient_id == owner_id),
                ),
                Friendship.status == FriendshipStatus.ACCEPTED,
            )
        )
        if is_friend is None:
            return Result.fail(
                "You can only add accepted friends to a group.", error_code="NOT_FRIENDS", status_code=403
            )

        existing = await self._db.scalar(
            select(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.user_id == dto.user_id,
                GroupMember.left_at.is_(None),
            )
        )
        if existing is not None:
            return Result.fail(
                "This user is already a member of the group.", error_code="ALREADY_MEMBER", status_code=409
            )

        active_count = await self._db.scalar(
            select(func.count()).select_from(GroupMember).where(
                GroupMember.group_id == group_id, GroupMember.left_at.is_(None)
            )
        )
        if (active_count or 0) >= FREE_MEMBER_LIMIT:
            return Result.fail(
                f"You have exceeded the limit of {FREE_MEMBER_LIMIT} maximum friends per group. Upgrade to Clara+ to add more.",
                status_code=402,
            )

        # No target_amount here — the owner assigns one afterward via
        # update_member, same as any other member's target.
        member = GroupMember(
            group_id=group_id,
            user_id=dto.user_id,
            target_amount=None,
            contributed_amount=Decimal(0),
            status=GroupMemberStatus.PENDING,
            invite_status=GroupInviteStatus.PENDING,
        )
        self._db.add(member)
        await self._db.commit()
        await self._db.refresh(member)

        return Result.ok(member_to_dto(member, target_user), status_code=201)

    async def update_member(
        self, owner_id: uuid.UUID, group_id: uuid.UUID, member_id: uuid.UUID, dto: UpdateMemberDto
    ) -> Result[GroupMemberResponseDto]:
        if not await self._is_owner(owner_id, group_id):
            return Result.fail("Group not found or you are not the owner.", status_code=404)

        member = await self._db.scalar(
            select(GroupMember).where(
                GroupMember.id == member_id,
                GroupMember.group_id == group_id,
                GroupMember.left_at.is_(None),
            )
        )
        if not member:
            return Result.fail("Member not found.", status_code=404)

        member.target_amount = dto.target_amount
        contributed = Decimal(str(member.contributed_amount or 0))
        member.status = (
            GroupMemberStatus.COMPLETE if contributed >= dto.target_amount else GroupMemberStatus.PENDING
        )
        await self._db.commit()

        user = await self._db.scalar(select(User).where(User.id == member.user_id))
        return Result.ok(member_to_dto(member, user))

    async def remove_member(
        self,
        owner_id: uuid.UUID,
        group_id: uuid.UUID,
        member_id: uuid.UUID,
        redistribution: RedistributionChoice,
    ) -> Result[None]:
        if not await self._is_owner(owner_id, group_id):
            return Result.fail("Group not found or you are not the owner.", status_code=404)

        member = await self._db.scalar(
            select(GroupMember).where(
                GroupMember.id == member_id,
                GroupMember.group_id == group_id,
                GroupMember.left_at.is_(None),
            )
        )
        if not member:
            return Result.fail("Member not found.", status_code=404)
        if member.user_id == owner_id:
            return Result.fail("Cannot remove yourself as the group owner.")

        unmet = Decimal(str(member.target_amount or 0)) - Decimal(str(member.contributed_amount or 0))
        unmet = max(Decimal(0), unmet)

        member.left_at = datetime.now(timezone.utc)
        member.status = GroupMemberStatus.REMOVED

        if unmet > 0:
            result = await self._db.execute(
                select(GroupMember).where(
                    GroupMember.group_id == group_id,
                    GroupMember.id != member_id,
                    GroupMember.left_at.is_(None),
                )
            )
            remaining_members = list(result.scalars().all())

            if redistribution == RedistributionChoice.SELF:
                owner_member = next((m for m in remaining_members if m.user_id == owner_id), None)
                if owner_member is not None:
                    self._add_to_target(owner_member, unmet)
            elif remaining_members:
                share = (unmet / len(remaining_members)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                for m in remaining_members:
                    self._add_to_target(m, share)

        await self._db.commit()
        return Result.ok(None)

    async def respond_to_invite(
        self, user_id: uuid.UUID, group_id: uuid.UUID, response: InviteResponse
    ) -> Result[Optional[GroupMemberResponseDto]]:
        group = await self._db.scalar(select(Group).where(Group.id == group_id))
        if not group:
            return Result.fail("Group not found.", status_code=404)

        member = await self._db.scalar(
            select(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.user_id == user_id,
                GroupMember.left_at.is_(None),
            )
        )
        if not member:
            return Result.fail("Invite not found.", status_code=404)
        if member.invite_status == GroupInviteStatus.DECLINED:
            return Result.fail("You already declined this invite.", status_code=409)

        if response == InviteResponse.ACCEPTED:
            member.invite_status = GroupInviteStatus.ACCEPTED
            await self._db.commit()
            user = await self._db.scalar(select(User).where(User.id == member.user_id))
            return Result.ok(member_to_dto(member, user))

        if group.owner_id == user_id:
            return Result.fail("You cannot decline your own group.")

        unmet = Decimal(str(member.target_amount or 0)) - Decimal(str(member.contributed_amount or 0))
        unmet = max(Decimal(0), unmet)

        member.invite_status = GroupInviteStatus.DECLINED
        member.status = GroupMemberStatus.REMOVED
        member.left_at = datetime.now(timezone.utc)

        if unmet > 0:
            owner_member = await self._db.scalar(
                select(GroupMember).where(
                    GroupMember.group_id == group_id,
                    GroupMember.user_id == group.owner_id,
                    GroupMember.left_at.is_(None),
                )
            )
            if owner_member is not None:
                self._add_to_target(owner_member, unmet)

        await self._db.commit()
        return Result.ok(None)

    @staticmethod
    def _add_to_target(member: GroupMember, amount: Decimal) -> None:
        new_target = Decimal(str(member.target_amount or 0)) + amount
        member.target_amount = new_target
        contributed = Decimal(str(member.contributed_amount or 0))
        member.status = (
            GroupMemberStatus.COMPLETE if contributed >= new_target else GroupMemberStatus.PENDING
        )

    async def _is_owner(self, user_id: uuid.UUID, group_id: uuid.UUID) -> bool:
        return bool(
            await self._db.scalar(
                select(Group).where(Group.id == group_id, Group.owner_id == user_id)
            )
        )


def get_group_member_service(db: AsyncSession = Depends(get_db)) -> GroupMemberService:
    return GroupMemberService(db)
