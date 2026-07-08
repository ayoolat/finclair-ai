import uuid
import calendar
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.dto.pagination import PageQueryDto
from app.common.response import PaginatedResponse, Result
from app.database.session import get_db
from app.module.budget.dto.budget import (
    AllocationResponseDto,
    BudgetResponseDto,
    CreateBudgetDto,
    UpdateBudgetDto,
    UpsertAllocationDto,
)
from app.module.budget.schema.budget import Budget
from app.module.budget.schema.budget_allocation import BudgetAllocation
from app.module.category.schema.category import Category
from app.module.expense.schema.expense import Expense
from app.module.expense.schema.expense_category import expense_categories
from app.module.insight.service.clara_service import ClaraService, get_clara_service


class BudgetService:
    def __init__(self, db: AsyncSession, clara: ClaraService) -> None:
        self._db = db
        self._clara = clara

    # ── List ──────────────────────────────────────────────────────────────────

    async def list_budgets(
        self, user_id: uuid.UUID, filters: PageQueryDto
    ) -> Result[PaginatedResponse[BudgetResponseDto]]:
        base = select(Budget).where(Budget.user_id == user_id)
        total = (await self._db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

        rows = await self._db.execute(
            base.options(selectinload(Budget.allocations).selectinload(BudgetAllocation.category))
            .order_by(Budget.start_date.desc())
            .offset(filters.offset)
            .limit(filters.page_size)
        )
        budgets = rows.scalars().all()
        dtos = [await self._to_dto(b, user_id) for b in budgets]
        return Result.ok(PaginatedResponse.ok(data=dtos, page=filters.page, page_size=filters.page_size, total=total))

    # ── Get ───────────────────────────────────────────────────────────────────

    async def get(self, user_id: uuid.UUID, budget_id: uuid.UUID) -> Result[BudgetResponseDto]:
        budget = await self._load(budget_id, user_id)
        if budget is None:
            return Result.fail("Budget not found.", error_code="NOT_FOUND", status_code=404)
        return Result.ok(await self._to_dto(budget, user_id))

    # ── Create ────────────────────────────────────────────────────────────────

    async def create(self, user_id: uuid.UUID, dto: CreateBudgetDto) -> Result[BudgetResponseDto]:
        today = date.today()
        start_date = today.replace(day=1)
        last_day = calendar.monthrange(today.year, today.month)[1]
        end_date = today.replace(day=last_day)

        existing = await self._db.execute(
            select(Budget).where(Budget.user_id == user_id, Budget.start_date == start_date)
        )
        if existing.scalar_one_or_none() is not None:
            return Result.fail(
                "A budget for this month already exists.",
                error_code="CONFLICT",
                status_code=409,
            )

        budget = Budget(
            user_id=user_id,
            amount_allocated=dto.amount_allocated,
            spent=Decimal("0"),
            remaining=dto.amount_allocated,
            start_date=start_date,
            end_date=end_date,
            created_by=user_id,
            updated_by=user_id,
        )
        self._db.add(budget)
        try:
            await self._db.commit()
        except IntegrityError:
            await self._db.rollback()
            return Result.fail(
                "A budget for this month already exists.",
                error_code="CONFLICT",
                status_code=409,
            )
        self._db.expire_all()
        budget = await self._load(budget.id, user_id)  # type: ignore[assignment]
        return Result.ok(await self._to_dto(budget, user_id), status_code=201)  # type: ignore[arg-type]

    # ── Update ────────────────────────────────────────────────────────────────

    async def update(
        self, user_id: uuid.UUID, budget_id: uuid.UUID, dto: UpdateBudgetDto
    ) -> Result[BudgetResponseDto]:
        budget = await self._load(budget_id, user_id)
        if budget is None:
            return Result.fail("Budget not found.", error_code="NOT_FOUND", status_code=404)

        if dto.amount_allocated is not None:
            budget.amount_allocated = dto.amount_allocated
            spent = await self._compute_budget_spent(user_id, budget)
            budget.spent = Decimal(str(spent))
            budget.remaining = dto.amount_allocated - Decimal(str(spent))
        budget.updated_by = user_id

        await self._db.commit()
        self._db.expire_all()
        budget = await self._load(budget_id, user_id)  # type: ignore[assignment]
        return Result.ok(await self._to_dto(budget, user_id))  # type: ignore[arg-type]

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete(self, user_id: uuid.UUID, budget_id: uuid.UUID) -> Result[dict]:
        budget = await self._load(budget_id, user_id)
        if budget is None:
            return Result.fail("Budget not found.", error_code="NOT_FOUND", status_code=404)
        await self._db.delete(budget)
        await self._db.commit()
        return Result.ok({"message": "Budget deleted."})

    # ── Insight ───────────────────────────────────────────────────────────────

    async def get_insight(self, user_id: uuid.UUID, budget_id: uuid.UUID) -> Result[str]:
        result = await self.get(user_id, budget_id)
        if result.is_err:
            return Result.fail(result.error, error_code="NOT_FOUND", status_code=result.status_code)
        return Result.ok(result.data.clara_insight)

    # ── Allocations ───────────────────────────────────────────────────────────

    async def upsert_allocation(
        self, user_id: uuid.UUID, budget_id: uuid.UUID, dto: UpsertAllocationDto
    ) -> Result[BudgetResponseDto]:
        budget = await self._load(budget_id, user_id)
        if budget is None:
            return Result.fail("Budget not found.", error_code="NOT_FOUND", status_code=404)

        category = await self._db.get(Category, dto.category_id)
        if category is None:
            return Result.fail("Category not found.", error_code="NOT_FOUND", status_code=404)
        if category.user_id is not None and category.user_id != user_id:
            return Result.fail("Category not found.", error_code="NOT_FOUND", status_code=404)

        existing = await self._db.execute(
            select(BudgetAllocation).where(
                BudgetAllocation.budget_id == budget_id,
                BudgetAllocation.category_id == dto.category_id,
            )
        )
        allocation = existing.scalar_one_or_none()
        if allocation is None:
            allocation = BudgetAllocation(
                budget_id=budget_id,
                category_id=dto.category_id,
                amount_allocated=dto.amount_allocated,
                created_by=user_id,
                updated_by=user_id,
            )
            self._db.add(allocation)
        else:
            allocation.amount_allocated = dto.amount_allocated
            allocation.updated_by = user_id

        await self._db.commit()
        self._db.expire_all()
        budget = await self._load(budget_id, user_id)  # type: ignore[assignment]
        return Result.ok(await self._to_dto(budget, user_id))  # type: ignore[arg-type]

    async def delete_allocation(
        self, user_id: uuid.UUID, budget_id: uuid.UUID, category_id: uuid.UUID
    ) -> Result[BudgetResponseDto]:
        budget = await self._load(budget_id, user_id)
        if budget is None:
            return Result.fail("Budget not found.", error_code="NOT_FOUND", status_code=404)

        existing = await self._db.execute(
            select(BudgetAllocation).where(
                BudgetAllocation.budget_id == budget_id,
                BudgetAllocation.category_id == category_id,
            )
        )
        allocation = existing.scalar_one_or_none()
        if allocation is None:
            return Result.fail("Allocation not found.", error_code="NOT_FOUND", status_code=404)

        await self._db.delete(allocation)
        await self._db.commit()
        self._db.expire_all()
        budget = await self._load(budget_id, user_id)  # type: ignore[assignment]
        return Result.ok(await self._to_dto(budget, user_id))  # type: ignore[arg-type]

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _load(self, budget_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Budget]:
        result = await self._db.execute(
            select(Budget)
            .where(Budget.id == budget_id, Budget.user_id == user_id)
            .options(selectinload(Budget.allocations).selectinload(BudgetAllocation.category))
        )
        return result.scalar_one_or_none()

    async def _compute_budget_spent(self, user_id: uuid.UUID, budget: Budget) -> float:
        start = datetime(budget.start_date.year, budget.start_date.month, budget.start_date.day)
        end = datetime(budget.end_date.year, budget.end_date.month, budget.end_date.day, 23, 59, 59)
        row = await self._db.execute(
            select(func.sum(Expense.amount)).where(
                Expense.user_id == user_id,
                Expense.deleted_at.is_(None),
                Expense.expense_date >= start,
                Expense.expense_date <= end,
            )
        )
        return float(row.scalar_one() or 0)

    async def _compute_category_spent(
        self, user_id: uuid.UUID, budget: Budget, category_id: uuid.UUID
    ) -> float:
        start = datetime(budget.start_date.year, budget.start_date.month, budget.start_date.day)
        end = datetime(budget.end_date.year, budget.end_date.month, budget.end_date.day, 23, 59, 59)
        row = await self._db.execute(
            select(func.sum(Expense.amount))
            .join(expense_categories, expense_categories.c.expense_id == Expense.id)
            .where(
                Expense.user_id == user_id,
                Expense.deleted_at.is_(None),
                Expense.expense_date >= start,
                Expense.expense_date <= end,
                expense_categories.c.category_id == category_id,
            )
        )
        return float(row.scalar_one() or 0)

    async def _to_dto(self, budget: Budget, user_id: uuid.UUID) -> BudgetResponseDto:
        spent = await self._compute_budget_spent(user_id, budget)
        allocated = float(budget.amount_allocated)
        remaining = max(0.0, allocated - spent)
        pct_used = (spent / allocated * 100) if allocated > 0 else 0.0

        allocation_dtos = []
        for alloc in budget.allocations:
            cat_spent = await self._compute_category_spent(user_id, budget, alloc.category_id)
            cat_allocated = float(alloc.amount_allocated)
            cat_remaining = max(0.0, cat_allocated - cat_spent)
            cat_pct = (cat_spent / cat_allocated * 100) if cat_allocated > 0 else 0.0
            allocation_dtos.append(
                AllocationResponseDto(
                    id=alloc.id,
                    category_id=alloc.category_id,
                    category_name=alloc.category.name,
                    category_icon=alloc.category.icon,
                    amount_allocated=cat_allocated,
                    spent=cat_spent,
                    remaining=cat_remaining,
                    pct_used=cat_pct,
                )
            )

        insight = self._clara.budget_insight(
            allocated=allocated,
            spent=spent,
            pct_used=pct_used,
            remaining=remaining,
            allocations=allocation_dtos,
        )

        return BudgetResponseDto(
            id=budget.id,
            amount_allocated=allocated,
            spent=spent,
            remaining=remaining,
            pct_used=pct_used,
            start_date=budget.start_date,
            end_date=budget.end_date,
            allocations=allocation_dtos,
            clara_insight=insight,
        )


def get_budget_service(
    db: AsyncSession = Depends(get_db),
    clara: ClaraService = Depends(get_clara_service),
) -> BudgetService:
    return BudgetService(db, clara)


