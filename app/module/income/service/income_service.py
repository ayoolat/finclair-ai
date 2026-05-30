import uuid
from typing import Optional

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums.income import IncomeSource
from app.common.response import Result
from app.database.session import get_db
from app.module.income.dto.income import (
    CreateCustomSourceDto,
    CreateIncomeDto,
    IncomeResponseDto,
    IncomeSourceDto,
    UpdateIncomeDto,
)
from app.module.income.schema.income import Income
from app.module.income.schema.income_source import UserIncomeSource

_DEFAULT_SOURCES = [s.value for s in IncomeSource]


class IncomeService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_sources(self, user_id: uuid.UUID) -> Result[list[IncomeSourceDto]]:
        result = await self._db.execute(
            select(UserIncomeSource).where(UserIncomeSource.user_id == user_id)
        )
        custom = [IncomeSourceDto(name=row.name, is_custom=True) for row in result.scalars().all()]
        defaults = [IncomeSourceDto(name=s, is_custom=False) for s in _DEFAULT_SOURCES]
        return Result.ok(defaults + custom)

    async def add_custom_source(
        self, user_id: uuid.UUID, dto: CreateCustomSourceDto
    ) -> Result[IncomeSourceDto]:
        existing = await self._db.execute(
            select(UserIncomeSource).where(
                UserIncomeSource.user_id == user_id,
                UserIncomeSource.name == dto.name,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return Result.fail("Source already exists.", error_code="SOURCE_EXISTS", status_code=409)

        source = UserIncomeSource(user_id=user_id, name=dto.name)
        self._db.add(source)
        await self._db.commit()
        return Result.ok(IncomeSourceDto(name=source.name, is_custom=True), status_code=201)

    async def get(self, user_id: uuid.UUID) -> Result[IncomeResponseDto]:
        income = await self._get_current(user_id)
        if income is None:
            return Result.fail("No income set up yet.", error_code="NOT_FOUND", status_code=404)
        return Result.ok(IncomeResponseDto.model_validate(income))

    async def upsert(self, user_id: uuid.UUID, dto: CreateIncomeDto) -> Result[IncomeResponseDto]:
        income = await self._get_current(user_id)
        if income is None:
            income = Income(user_id=user_id)
            self._db.add(income)

        income.amount = dto.amount  # type: ignore[union-attr]
        income.source = dto.source  # type: ignore[union-attr]
        income.reoccurrence = dto.reoccurrence.value  # type: ignore[union-attr]
        income.note = dto.note  # type: ignore[union-attr]
        income.start_date = dto.start_date  # type: ignore[union-attr]

        await self._db.commit()
        await self._db.refresh(income)
        return Result.ok(IncomeResponseDto.model_validate(income), status_code=201)

    async def update(self, user_id: uuid.UUID, dto: UpdateIncomeDto) -> Result[IncomeResponseDto]:
        income = await self._get_current(user_id)
        if income is None:
            return Result.fail("No income set up yet.", error_code="NOT_FOUND", status_code=404)

        if dto.amount is not None:
            income.amount = dto.amount
        if dto.source is not None:
            income.source = dto.source.strip()
        if dto.reoccurrence is not None:
            income.reoccurrence = dto.reoccurrence.value
        if dto.note is not None:
            income.note = dto.note
        if dto.start_date is not None:
            income.start_date = dto.start_date

        await self._db.commit()
        await self._db.refresh(income)
        return Result.ok(IncomeResponseDto.model_validate(income))

    async def _get_current(self, user_id: uuid.UUID) -> Optional[Income]:
        result = await self._db.execute(
            select(Income)
            .where(Income.user_id == user_id)
            .order_by(Income.start_date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


def get_income_service(db: AsyncSession = Depends(get_db)) -> IncomeService:
    return IncomeService(db)
