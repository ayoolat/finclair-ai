import uuid
from decimal import Decimal
from typing import Optional

from fastapi import Depends, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.dto.pagination import PageQueryDto
from app.common.enums.groups import GroupMemberStatus
from app.common.ocr.factory import get_ocr_provider
from app.common.response import PaginatedResponse, Result
from app.common.storage.factory import get_storage_provider
from app.database.session import get_db
from app.module.groups.dto.group import RecordSavingsDto, SavingsEntryResponseDto
from app.module.groups.schema.group_member import GroupMember
from app.module.groups.schema.group_savings_entry import GroupSavingsEntry
from app.module.groups.service._helpers import receipt_amount_matches


class GroupSavingsService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._storage = get_storage_provider()
        self._ocr = get_ocr_provider()

    async def record_savings(
        self,
        user_id: uuid.UUID,
        group_id: uuid.UUID,
        dto: RecordSavingsDto,
        receipt: Optional[UploadFile] = None,
    ) -> Result[SavingsEntryResponseDto]:
        member = await self._member_or_fail(user_id, group_id)
        if not member:
            return Result.fail("You are not a member of this group.", status_code=403)

        file_url: Optional[str] = None
        if receipt:
            data = await receipt.read()
            content_type = receipt.content_type or "image/jpeg"

            try:
                ocr_result = await self._ocr.parse_receipt(data, content_type)
            except ValueError as exc:
                return Result.fail(str(exc), error_code="INVALID_IMAGE", status_code=400)
            except RuntimeError as exc:
                return Result.fail(
                    f"Could not verify the receipt: {exc}", error_code="OCR_FAILED", status_code=502
                )

            if not receipt_amount_matches(dto.amount, ocr_result.total):
                return Result.fail(
                    f"The receipt shows {ocr_result.total}, which doesn't match the "
                    f"{dto.amount} you reported. Please correct the amount or upload the matching receipt.",
                    error_code="RECEIPT_AMOUNT_MISMATCH",
                    status_code=422,
                )

            ext = (receipt.filename or "file").rsplit(".", 1)[-1]
            file_name = f"{uuid.uuid4()}.{ext}"
            await self._storage.upload(f"groups/{group_id}/receipts", file_name, data, content_type)
            file_url = self._storage.public_url(f"groups/{group_id}/receipts", file_name)

        contributed = Decimal(str(member.contributed_amount or 0)) + dto.amount
        member.contributed_amount = contributed
        if member.target_amount and contributed >= Decimal(str(member.target_amount)):
            member.status = GroupMemberStatus.COMPLETE

        entry = GroupSavingsEntry(
            group_id=group_id,
            member_id=member.id,
            user_id=user_id,
            amount=dto.amount,
            cumulative_at_time=contributed,
            note=dto.note,
            file_url=file_url,
        )
        self._db.add(entry)
        await self._db.commit()
        await self._db.refresh(entry)
        return Result.ok(SavingsEntryResponseDto.model_validate(entry), status_code=201)

    async def list_savings(
        self, user_id: uuid.UUID, group_id: uuid.UUID, filters: PageQueryDto
    ) -> Result[PaginatedResponse[SavingsEntryResponseDto]]:
        if not await self._member_or_fail(user_id, group_id):
            return Result.fail("You are not a member of this group.", status_code=403)

        base = select(GroupSavingsEntry).where(GroupSavingsEntry.group_id == group_id)
        total = (await self._db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

        result = await self._db.execute(
            base.order_by(GroupSavingsEntry.recorded_at.desc())
            .offset(filters.offset)
            .limit(filters.page_size)
        )
        entries = result.scalars().all()
        dtos = [SavingsEntryResponseDto.model_validate(e) for e in entries]
        return Result.ok(PaginatedResponse.ok(data=dtos, page=filters.page, page_size=filters.page_size, total=total))

    async def _member_or_fail(self, user_id: uuid.UUID, group_id: uuid.UUID) -> Optional[GroupMember]:
        return await self._db.scalar(
            select(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.user_id == user_id,
                GroupMember.left_at.is_(None),
            )
        )


def get_group_savings_service(db: AsyncSession = Depends(get_db)) -> GroupSavingsService:
    return GroupSavingsService(db)
