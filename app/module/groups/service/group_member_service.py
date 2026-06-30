import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.enums.groups import GroupMemberStatus
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
        self, owner_id: uuid.UUID, group_id: uuid.UUID, member_id: uuid.UUID
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

        member.left_at = datetime.now(timezone.utc)
        member.status = GroupMemberStatus.REMOVED
        await self._db.commit()
        return Result.ok(None)

    async def _is_owner(self, user_id: uuid.UUID, group_id: uuid.UUID) -> bool:
        return bool(
            await self._db.scalar(
                select(Group).where(Group.id == group_id, Group.owner_id == user_id)
            )
        )


def get_group_member_service(db: AsyncSession = Depends(get_db)) -> GroupMemberService:
    return GroupMemberService(db)
