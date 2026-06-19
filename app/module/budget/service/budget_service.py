import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.response import Result
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


class BudgetService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── List ──────────────────────────────────────────────────────────────────

    async def list_budgets(self, user_id: uuid.UUID) -> Result[list[BudgetResponseDto]]:
        rows = await self._db.execute(
            select(Budget)
            .where(Budget.user_id == user_id)
            .options(selectinload(Budget.allocations).selectinload(BudgetAllocation.category))
            .order_by(Budget.start_date.desc())
        )
        budgets = rows.scalars().all()
        result = [await self._to_dto(b, user_id) for b in budgets]
        return Result.ok(result)

    # ── Get ───────────────────────────────────────────────────────────────────

    async def get(self, user_id: uuid.UUID, budget_id: uuid.UUID) -> Result[BudgetResponseDto]:
        budget = await self._load(budget_id, user_id)
        if budget is None:
            return Result.fail("Budget not found.", error_code="NOT_FOUND", status_code=404)
        return Result.ok(await self._to_dto(budget, user_id))

    # ── Create ────────────────────────────────────────────────────────────────

    async def create(self, user_id: uuid.UUID, dto: CreateBudgetDto) -> Result[BudgetResponseDto]:
        budget = Budget(
            user_id=user_id,
            name=dto.name,
            amount_allocated=dto.amount_allocated,
            spent=Decimal("0"),
            remaining=dto.amount_allocated,
            start_date=dto.start_date,
            end_date=dto.end_date,
            created_by=user_id,
            updated_by=user_id,
        )
        self._db.add(budget)
        await self._db.commit()
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

        if dto.name is not None:
            budget.name = dto.name
        if dto.amount_allocated is not None:
            budget.amount_allocated = dto.amount_allocated
            spent = await self._compute_budget_spent(user_id, budget)
            budget.spent = Decimal(str(spent))
            budget.remaining = dto.amount_allocated - Decimal(str(spent))
        if dto.start_date is not None:
            budget.start_date = dto.start_date
        if dto.end_date is not None:
            budget.end_date = dto.end_date
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
                    amount_allocated=cat_allocated,
                    spent=cat_spent,
                    remaining=cat_remaining,
                    pct_used=cat_pct,
                )
            )

        return BudgetResponseDto(
            id=budget.id,
            name=budget.name,
            amount_allocated=allocated,
            spent=spent,
            remaining=remaining,
            pct_used=pct_used,
            start_date=budget.start_date,
            end_date=budget.end_date,
            allocations=allocation_dtos,
        )


def get_budget_service(db: AsyncSession = Depends(get_db)) -> BudgetService:
    return BudgetService(db)
