import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.dto.pagination import PageQueryDto
from app.common.enums.groups import GroupInviteStatus, GroupMemberStatus
from app.common.response import PaginatedResponse, Result
from app.database.session import get_db
from app.module.groups.dto.group import CreateGroupDto, GroupDetailResponseDto, GroupResponseDto, UpdateGroupDto
from app.module.groups.schema.group import Group
from app.module.groups.schema.group_member import GroupMember
from app.module.groups.service._helpers import group_to_dto, member_to_dto, shareable_link
from app.module.user.schema.user import User

FREE_GROUP_LIMIT = 2
FREE_MEMBER_LIMIT = 10


class GroupService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_groups(
        self, user_id: uuid.UUID, filters: PageQueryDto
    ) -> Result[PaginatedResponse[GroupResponseDto]]:
        base = (
            select(Group.id)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .where(GroupMember.user_id == user_id, GroupMember.left_at.is_(None))
        )
        total = (await self._db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

        result = await self._db.execute(
            select(Group)
            .options(selectinload(Group.members))
            .join(GroupMember, GroupMember.group_id == Group.id)
            .where(GroupMember.user_id == user_id, GroupMember.left_at.is_(None))
            .order_by(Group.created_at.desc())
            .offset(filters.offset)
            .limit(filters.page_size)
        )
        groups = result.scalars().unique().all()
        dtos = [group_to_dto(g, [m for m in g.members if m.left_at is None], user_id) for g in groups]
        return Result.ok(PaginatedResponse.ok(data=dtos, page=filters.page, page_size=filters.page_size, total=total))

    async def create_group(self, user_id: uuid.UUID, dto: CreateGroupDto) -> Result[GroupDetailResponseDto]:
        count = await self._db.scalar(
            select(func.count()).select_from(GroupMember).where(
                GroupMember.user_id == user_id,
                GroupMember.left_at.is_(None),
            )
        )
        if (count or 0) >= FREE_GROUP_LIMIT:
            return Result.fail(
                f"You have exceeded the limit of {FREE_GROUP_LIMIT} maximum groups. Upgrade to Clara+ to add more groups.",
                status_code=402,
            )

        all_member_ids = [user_id] + [mid for mid in dto.member_ids if mid != user_id]
        if len(all_member_ids) > FREE_MEMBER_LIMIT:
            return Result.fail(
                f"You have exceeded the limit of {FREE_MEMBER_LIMIT} maximum friends per group. Upgrade to Clara+ to add more.",
                status_code=402,
            )

        group = Group(name=dto.name, target_amount=dto.target_amount, end_date=dto.end_date, owner_id=user_id)
        self._db.add(group)
        await self._db.flush()

        per_member_target = dto.target_amount / len(all_member_ids) if all_member_ids else None
        members = [
            GroupMember(
                group_id=group.id,
                user_id=mid,
                target_amount=per_member_target,
                contributed_amount=Decimal(0),
                status=GroupMemberStatus.PENDING,
                invite_status=GroupInviteStatus.ACCEPTED if mid == user_id else GroupInviteStatus.PENDING,
            )
            for mid in all_member_ids
        ]
        self._db.add_all(members)
        await self._db.commit()
        await self._db.refresh(group)

        user_map = await self._load_user_map([m.user_id for m in members])
        member_dtos = [member_to_dto(m, user_map[m.user_id]) for m in members if m.user_id in user_map]
        return Result.ok(
            GroupDetailResponseDto(**group_to_dto(group, members, user_id).model_dump(), members=member_dtos),
            status_code=201,
        )

    async def get_group(self, user_id: uuid.UUID, group_id: uuid.UUID) -> Result[GroupDetailResponseDto]:
        result = await self._db.execute(
            select(Group).options(selectinload(Group.members)).where(Group.id == group_id)
        )
        group = result.scalar_one_or_none()
        if not group:
            return Result.fail("Group not found.", status_code=404)

        active = [m for m in group.members if m.left_at is None]
        viewer_member = next((m for m in active if m.user_id == user_id), None)
        if viewer_member is None:
            return Result.fail("You are not a member of this group.", status_code=403)
        if user_id != group.owner_id and viewer_member.invite_status != GroupInviteStatus.ACCEPTED:
            return Result.fail("Accept the group invite to view this group.", status_code=403)

        user_map = await self._load_user_map([m.user_id for m in active])
        member_dtos = [member_to_dto(m, user_map[m.user_id]) for m in active if m.user_id in user_map]
        return Result.ok(GroupDetailResponseDto(**group_to_dto(group, active, user_id).model_dump(), members=member_dtos))

    async def update_group(self, user_id: uuid.UUID, group_id: uuid.UUID, dto: UpdateGroupDto) -> Result[GroupResponseDto]:
        group = await self._owned_group(user_id, group_id)
        if not group:
            return Result.fail("Group not found or you are not the owner.", status_code=404)
        if dto.name is not None:
            group.name = dto.name
        if dto.target_amount is not None:
            group.target_amount = dto.target_amount
        if dto.end_date is not None:
            group.end_date = dto.end_date
        await self._db.commit()
        await self._db.refresh(group, ["members"])
        active = [m for m in group.members if m.left_at is None]
        return Result.ok(group_to_dto(group, active, user_id))

    async def delete_group(self, user_id: uuid.UUID, group_id: uuid.UUID) -> Result[None]:
        group = await self._owned_group(user_id, group_id)
        if not group:
            return Result.fail("Group not found or you are not the owner.", status_code=404)
        await self._db.delete(group)
        await self._db.commit()
        return Result.ok(None)

    async def leave_group(self, user_id: uuid.UUID, group_id: uuid.UUID) -> Result[None]:
        group = await self._db.scalar(select(Group).where(Group.id == group_id))
        if not group:
            return Result.fail("Group not found.", status_code=404)
        if group.owner_id == user_id:
            return Result.fail("Owner cannot leave the group. Delete the group instead.")

        member = await self._db.scalar(
            select(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.user_id == user_id,
                GroupMember.left_at.is_(None),
            )
        )
        if not member:
            return Result.fail("You are not a member of this group.", status_code=404)

        member.left_at = datetime.now(timezone.utc)
        member.status = GroupMemberStatus.LEFT
        await self._db.commit()
        return Result.ok(None)

    async def get_share_link(self, user_id: uuid.UUID, group_id: uuid.UUID) -> Result[dict]:
        is_member = await self._db.scalar(
            select(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.user_id == user_id,
                GroupMember.left_at.is_(None),
            )
        )
        if not is_member:
            return Result.fail("You are not a member of this group.", status_code=403)
        return Result.ok({"group_id": str(group_id), "link": shareable_link(group_id)})

    async def _owned_group(self, user_id: uuid.UUID, group_id: uuid.UUID) -> Optional[Group]:
        return await self._db.scalar(
            select(Group)
            .options(selectinload(Group.members))
            .where(Group.id == group_id, Group.owner_id == user_id)
        )

    async def _load_user_map(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, User]:
        result = await self._db.execute(select(User).where(User.id.in_(user_ids)))
        return {u.id: u for u in result.scalars().all()}


def get_group_service(db: AsyncSession = Depends(get_db)) -> GroupService:
    return GroupService(db)
