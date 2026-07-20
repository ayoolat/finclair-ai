import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.enums.groups import GroupMemberStatus, RedistributionChoice
from app.common.response import Result
from app.database.session import get_db
from app.module.groups.dto.group import GroupMemberResponseDto, UpdateMemberDto
from app.module.groups.schema.group import Group
from app.module.groups.schema.group_member import GroupMember
from app.module.groups.service._helpers import member_to_dto
from app.module.user.schema.user import User


class GroupMemberService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

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
