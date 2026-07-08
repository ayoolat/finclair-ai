import uuid
from typing import Optional

from fastapi import Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.common.dto.pagination import PageQueryDto
from app.common.enums.income import IncomeReoccurrence
from app.common.response import PaginatedResponse, Result
from app.database.session import get_db
from app.module.income.dto.income import (
    CreateCustomSourceDto,
    CreateIncomeDto,
    IncomeCalculationDto,
    IncomeResponseDto,
    IncomeSourceDto,
    UpdateIncomeAmountDto,
    UpdateIncomeDto,
)
from app.module.income.schema.income import Income
from app.module.income.schema.income_source import IncomeSource

# Monthly equivalent multipliers for each recurrence type
_TO_MONTHLY = {
    IncomeReoccurrence.DAILY: 30,
    IncomeReoccurrence.WEEKLY: 4,
    IncomeReoccurrence.MONTHLY: 1,
    IncomeReoccurrence.ONE_TIME: 0,  # excluded from recurring calculation
}


class IncomeService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_sources(
        self, user_id: uuid.UUID, filters: PageQueryDto
    ) -> Result[PaginatedResponse[IncomeSourceDto]]:
        base = select(IncomeSource).where(
            or_(IncomeSource.user_id == user_id, IncomeSource.is_default == True)  # noqa: E712
        )
        total = (await self._db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

        result = await self._db.execute(
            base.order_by(IncomeSource.is_default.desc(), IncomeSource.name)
            .offset(filters.offset)
            .limit(filters.page_size)
        )
        sources = [
            IncomeSourceDto(id=row.id, name=row.name, is_default=row.is_default)
            for row in result.scalars().all()
        ]
        return Result.ok(PaginatedResponse.ok(data=sources, page=filters.page, page_size=filters.page_size, total=total))

    async def add_custom_source(
        self, user_id: uuid.UUID, dto: CreateCustomSourceDto
    ) -> Result[IncomeSourceDto]:
        existing = await self._db.execute(
            select(IncomeSource).where(
                IncomeSource.user_id == user_id,
                IncomeSource.name == dto.name,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return Result.fail("Source already exists.", error_code="SOURCE_EXISTS", status_code=409)

        source = IncomeSource(user_id=user_id, name=dto.name, is_default=False, created_by=user_id)
        self._db.add(source)
        await self._db.commit()
        await self._db.refresh(source)
        return Result.ok(IncomeSourceDto(id=source.id, name=source.name, is_default=False), status_code=201)

    async def calculate(self, user_id: uuid.UUID) -> Result[IncomeCalculationDto]:
        rows = await self._db.execute(
            select(Income.amount, Income.reoccurrence).where(Income.user_id == user_id)
        )
        monthly = 0.0
        for amount, reoccurrence in rows.all():
            rec = IncomeReoccurrence(reoccurrence)
            multiplier = _TO_MONTHLY.get(rec, 0)
            monthly += float(amount) * multiplier

        return Result.ok(IncomeCalculationDto(
            monthly=monthly,
            annual=monthly * 12,
            weekly=monthly / 4.33,
            daily=monthly / 30,
        ))

    async def get(self, user_id: uuid.UUID) -> Result[IncomeResponseDto]:
        income = await self._get_current(user_id)
        if income is None:
            return Result.fail("No income set up yet.", error_code="NOT_FOUND", status_code=404)
        return Result.ok(self._to_dto(income))

    async def upsert(self, user_id: uuid.UUID, dto: CreateIncomeDto) -> Result[IncomeResponseDto]:
        source = await self._validate_source(user_id, dto.source_id)
        if source is None:
            return Result.fail("Invalid source.", error_code="INVALID_SOURCE", status_code=400)

        income = await self._get_current(user_id)
        if income is None:
            income = Income(user_id=user_id, created_by=user_id)
            self._db.add(income)

        income.source_id = dto.source_id  # type: ignore[union-attr]
        income.amount = dto.amount  # type: ignore[union-attr]
        income.reoccurrence = dto.reoccurrence.value  # type: ignore[union-attr]
        income.note = dto.note  # type: ignore[union-attr]
        income.start_date = dto.start_date  # type: ignore[union-attr]
        income.updated_by = user_id  # type: ignore[union-attr]

        await self._db.commit()
        income = await self._get_current(user_id)
        return Result.ok(self._to_dto(income), status_code=201)  # type: ignore[arg-type]

    async def update_by_id(
        self, user_id: uuid.UUID, income_id: uuid.UUID, dto: UpdateIncomeAmountDto
    ) -> Result[IncomeResponseDto]:
        result = await self._db.execute(
            select(Income)
            .where(Income.id == income_id, Income.user_id == user_id)
            .options(joinedload(Income.source))
        )
        income = result.scalar_one_or_none()
        if income is None:
            return Result.fail("Income not found.", error_code="NOT_FOUND", status_code=404)

        income.amount = dto.amount
        income.updated_by = user_id
        await self._db.commit()
        await self._db.refresh(income)
        return Result.ok(self._to_dto(income))

    async def update(self, user_id: uuid.UUID, dto: UpdateIncomeDto) -> Result[IncomeResponseDto]:
        income = await self._get_current(user_id)
        if income is None:
            return Result.fail("No income set up yet.", error_code="NOT_FOUND", status_code=404)
        return await self._apply_update(user_id, income, dto)

    async def _apply_update(
        self, user_id: uuid.UUID, income: Income, dto: UpdateIncomeDto
    ) -> Result[IncomeResponseDto]:
        if dto.source_id is not None:
            source = await self._validate_source(user_id, dto.source_id)
            if source is None:
                return Result.fail("Invalid source.", error_code="INVALID_SOURCE", status_code=400)
            income.source_id = dto.source_id
        if dto.amount is not None:
            income.amount = dto.amount
        if dto.reoccurrence is not None:
            income.reoccurrence = dto.reoccurrence.value
        if dto.note is not None:
            income.note = dto.note
        if dto.start_date is not None:
            income.start_date = dto.start_date
        income.updated_by = user_id

        await self._db.commit()
        await self._db.refresh(income)
        return Result.ok(self._to_dto(income))

    # ------------------------------------------------------------------

    def _to_dto(self, income: Income) -> IncomeResponseDto:
        return IncomeResponseDto(
            id=income.id,
            amount=income.amount,
            source_id=income.source_id,
            source_name=income.source.name,
            reoccurrence=income.reoccurrence,
            note=income.note,
            start_date=income.start_date,
        )

    async def _get_current(self, user_id: uuid.UUID) -> Optional[Income]:
        result = await self._db.execute(
            select(Income)
            .where(Income.user_id == user_id)
            .options(joinedload(Income.source))
            .order_by(Income.start_date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _validate_source(
        self, user_id: uuid.UUID, source_id: uuid.UUID
    ) -> Optional[IncomeSource]:
        result = await self._db.execute(
            select(IncomeSource).where(
                IncomeSource.id == source_id,
                or_(IncomeSource.user_id == user_id, IncomeSource.is_default == True),  # noqa: E712
            )
        )
        return result.scalar_one_or_none()


def get_income_service(db: AsyncSession = Depends(get_db)) -> IncomeService:
    return IncomeService(db)
