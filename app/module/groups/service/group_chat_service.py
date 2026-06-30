import uuid
from decimal import Decimal
from typing import Optional

from fastapi import Depends, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums.groups import GroupMemberStatus, MessageRole, MessageType
from app.common.response import Result
from app.common.storage.factory import get_storage_provider
from app.database.session import get_db
from app.module.groups.dto.group import MessageResponseDto, SendMessageDto
from app.module.groups.schema.group_member import GroupMember
from app.module.groups.schema.group_message import GroupMessage
from app.module.groups.schema.group_savings_entry import GroupSavingsEntry
from app.module.user.schema.user import User


def _build_message_dto(msg: GroupMessage, user_map: dict[uuid.UUID, User]) -> MessageResponseDto:
    sender = user_map.get(msg.sender_id) if msg.sender_id else None
    return MessageResponseDto(
        id=msg.id,
        group_id=msg.group_id,
        sender_id=msg.sender_id,
        sender_username=sender.username if sender else None,
        role=MessageRole(msg.role),
        message_type=MessageType(msg.message_type),
        content=msg.content,
        file_url=msg.file_url,
        extra_data=msg.extra_data,
        sent_at=msg.sent_at,
    )


class GroupChatService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._storage = get_storage_provider()

    async def list_messages(
        self, user_id: uuid.UUID, group_id: uuid.UUID, page: int = 1, limit: int = 50
    ) -> Result[list[MessageResponseDto]]:
        if not await self._is_member(user_id, group_id):
            return Result.fail("You are not a member of this group.", status_code=403)

        offset = (page - 1) * limit
        result = await self._db.execute(
            select(GroupMessage)
            .where(GroupMessage.group_id == group_id, GroupMessage.deleted_at.is_(None))
            .order_by(GroupMessage.sent_at.asc())
            .offset(offset)
            .limit(limit)
        )
        messages = result.scalars().all()
        user_map = await self._load_senders(messages)
        return Result.ok([_build_message_dto(m, user_map) for m in messages])

    async def send_text(
        self, user_id: uuid.UUID, group_id: uuid.UUID, dto: SendMessageDto
    ) -> Result[MessageResponseDto]:
        if not await self._is_member(user_id, group_id):
            return Result.fail("You are not a member of this group.", status_code=403)

        msg = GroupMessage(
            group_id=group_id,
            sender_id=user_id,
            role=MessageRole.USER,
            message_type=MessageType.TEXT,
            content=dto.content,
        )
        self._db.add(msg)
        await self._db.commit()
        await self._db.refresh(msg)

        user_map = await self._load_senders([msg])
        return Result.ok(_build_message_dto(msg, user_map), status_code=201)

    async def send_attachment(
        self,
        user_id: uuid.UUID,
        group_id: uuid.UUID,
        file: UploadFile,
        record_amount: Optional[Decimal] = None,
    ) -> Result[MessageResponseDto]:
        if not await self._is_member(user_id, group_id):
            return Result.fail("You are not a member of this group.", status_code=403)

        data = await file.read()
        ext = (file.filename or "file").rsplit(".", 1)[-1]
        file_name = f"{uuid.uuid4()}.{ext}"
        await self._storage.upload(
            f"groups/{group_id}/chat", file_name, data, file.content_type or "image/jpeg"
        )
        file_url = self._storage.public_url(f"groups/{group_id}/chat", file_name)

        msg = GroupMessage(
            group_id=group_id,
            sender_id=user_id,
            role=MessageRole.USER,
            message_type=MessageType.IMAGE,
            file_url=file_url,
        )
        self._db.add(msg)
        await self._db.flush()

        if record_amount and record_amount > 0:
            await self._record_savings_from_attachment(user_id, group_id, record_amount, file_url)

        await self._db.commit()
        await self._db.refresh(msg)

        user_map = await self._load_senders([msg])
        return Result.ok(_build_message_dto(msg, user_map), status_code=201)

    async def _record_savings_from_attachment(
        self,
        user_id: uuid.UUID,
        group_id: uuid.UUID,
        amount: Decimal,
        file_url: str,
    ) -> None:
        member = await self._db.scalar(
            select(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.user_id == user_id,
                GroupMember.left_at.is_(None),
            )
        )
        if not member:
            return

        contributed = Decimal(str(member.contributed_amount or 0)) + amount
        member.contributed_amount = contributed
        if member.target_amount and contributed >= Decimal(str(member.target_amount)):
            member.status = GroupMemberStatus.COMPLETE

        self._db.add(
            GroupSavingsEntry(
                group_id=group_id,
                member_id=member.id,
                user_id=user_id,
                amount=amount,
                cumulative_at_time=contributed,
                file_url=file_url,
            )
        )

    async def _is_member(self, user_id: uuid.UUID, group_id: uuid.UUID) -> bool:
        return bool(
            await self._db.scalar(
                select(GroupMember).where(
                    GroupMember.group_id == group_id,
                    GroupMember.user_id == user_id,
                    GroupMember.left_at.is_(None),
                )
            )
        )

    async def _load_senders(self, messages: list[GroupMessage]) -> dict[uuid.UUID, User]:
        sender_ids = list({m.sender_id for m in messages if m.sender_id})
        if not sender_ids:
            return {}
        result = await self._db.execute(select(User).where(User.id.in_(sender_ids)))
        return {u.id: u for u in result.scalars().all()}


def get_group_chat_service(db: AsyncSession = Depends(get_db)) -> GroupChatService:
    return GroupChatService(db)
