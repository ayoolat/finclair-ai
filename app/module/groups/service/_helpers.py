import uuid
from datetime import date
from decimal import Decimal

from app.core.config import settings
from app.module.groups.dto.group import GroupMemberResponseDto, GroupResponseDto
from app.module.groups.schema.group import Group
from app.module.groups.schema.group_member import GroupMember
from app.common.enums.groups import GroupInviteStatus, GroupMemberStatus
from app.module.user.schema.user import User


def days_left(end_date: date) -> int:
    return max(0, (end_date - date.today()).days)


def savings_progress(raised: Decimal, target: Decimal) -> float:
    if target <= 0:
        return 0.0
    return round(float(raised / target) * 100, 1)


def shareable_link(group_id: uuid.UUID) -> str:
    base = getattr(settings, "frontend_url", "https://finclar.ai")
    return f"{base}/e/{group_id}"


_RECEIPT_AMOUNT_TOLERANCE_PCT = Decimal("0.01")  # 1% allowed drift (rounding, OCR noise)
_RECEIPT_AMOUNT_TOLERANCE_MIN = Decimal("0.01")  # minimum absolute tolerance


def receipt_amount_matches(claimed: Decimal, detected: Decimal) -> bool:
    tolerance = max(_RECEIPT_AMOUNT_TOLERANCE_MIN, claimed * _RECEIPT_AMOUNT_TOLERANCE_PCT)
    return abs(claimed - detected) <= tolerance




def group_to_dto(group: Group, members: list[GroupMember], viewer_id: uuid.UUID) -> GroupResponseDto:
    total_raised = sum(Decimal(str(m.contributed_amount or 0)) for m in members)
    target = Decimal(str(group.target_amount))

    viewer_member = next((m for m in members if m.user_id == viewer_id), None)
    if viewer_id == group.owner_id:
        amount_paid, amount_assigned = total_raised, target
        viewer_invite_status = GroupInviteStatus.ACCEPTED
    else:
        amount_paid = Decimal(str(viewer_member.contributed_amount or 0)) if viewer_member else Decimal(0)
        amount_assigned = (
            Decimal(str(viewer_member.target_amount))
            if viewer_member and viewer_member.target_amount is not None
            else Decimal(0)
        )
        viewer_invite_status = (
            GroupInviteStatus(viewer_member.invite_status) if viewer_member else GroupInviteStatus.PENDING
        )

    return GroupResponseDto(
        id=group.id,
        name=group.name,
        target_amount=target,
        end_date=group.end_date,
        owner_id=group.owner_id,
        created_at=group.created_at,
        invite_status=viewer_invite_status,
        total_raised=total_raised,
        balance=max(Decimal(0), target - total_raised),
        days_left=days_left(group.end_date),
        member_count=len(members),
        progress_percent=savings_progress(total_raised, target),
        shareable_link=shareable_link(group.id),
        amount_paid=amount_paid,
        amount_left=max(Decimal(0), amount_assigned - amount_paid),
        amount_assigned=amount_assigned,
    )


def member_to_dto(member: GroupMember, user: User) -> GroupMemberResponseDto:
    return GroupMemberResponseDto(
        id=member.id,
        user_id=member.user_id,
        username=user.username,
        profile_icon=user.profile_icon,
        status=GroupMemberStatus(member.status),
        invite_status=GroupInviteStatus(member.invite_status),
        target_amount=Decimal(str(member.target_amount)) if member.target_amount is not None else None,
        contributed_amount=Decimal(str(member.contributed_amount or 0)),
        joined_at=member.joined_at,
    )
