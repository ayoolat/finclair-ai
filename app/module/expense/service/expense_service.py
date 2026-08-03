import uuid
from calendar import month_abbr
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import Depends, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.enums.expense import ExpenseDirection, ExpenseStatus, ExpenseType
from app.common.enums.income import IncomeReoccurrence
from app.common.ocr.factory import get_ocr_provider
from app.common.response import PaginatedResponse, Result
from app.common.storage.factory import get_storage_provider
from app.database.session import get_db
from app.module.category.schema.category import Category
from app.module.expense.dto.expense import (
    CategoryExpenseSummaryDto,
    CreateManualExpenseDto,
    ExpenseFilterDto,
    ExpenseResponseDto,
    ExpenseSummaryDto,
    IncomeExpenseTrendPointDto,
    MonthlyTrendPointDto,
    UpdateExpenseDto,
)
from app.module.expense.schema.expense import Expense
from app.module.expense.schema.expense_category import expense_categories
from app.module.expense.schema.expense_item import ExpenseItem
from app.module.file.schema.file import File
from app.module.income.schema.income import Income
from app.module.insight.service.clara_service import ClaraService, get_clara_service

_RECEIPT_LOW_CONFIDENCE = 0.5


class ExpenseService:
    def __init__(self, db: AsyncSession, clara: ClaraService) -> None:
        self._db = db
        self._clara = clara
        self._storage = get_storage_provider()
        self._ocr = get_ocr_provider()

    # ── List ──────────────────────────────────────────────────────────────────

    async def list_expenses(
        self, user_id: uuid.UUID, filters: ExpenseFilterDto
    ) -> Result[PaginatedResponse[ExpenseResponseDto]]:
        base = select(Expense).where(
            Expense.user_id == user_id,
            Expense.deleted_at.is_(None),
        )

        if filters.search:
            base = base.where(Expense.description.ilike(f"%{filters.search}%"))
        if filters.source:
            base = base.where(Expense.source == filters.source)
        if filters.status:
            base = base.where(Expense.status == filters.status.value)
        if filters.start_date:
            base = base.where(Expense.expense_date >= filters.start_date)
        if filters.end_date:
            base = base.where(Expense.expense_date <= filters.end_date)
        if filters.category_id:
            base = base.where(
                Expense.id.in_(
                    select(expense_categories.c.expense_id).where(
                        expense_categories.c.category_id == filters.category_id
                    )
                )
            )

        total = (await self._db.execute(
            select(func.count()).select_from(base.subquery())
        )).scalar_one()

        sort_col = {
            "expense_date": Expense.expense_date,
            "amount": Expense.amount,
            "created_at": Expense.created_at,
        }.get(filters.order_by, Expense.expense_date)
        ordered = sort_col.desc() if filters.order_dir == "desc" else sort_col.asc()

        rows = await self._db.execute(
            base.options(
                selectinload(Expense.categories),
                selectinload(Expense.items),
                selectinload(Expense.file),
            )
            .order_by(ordered)
            .limit(filters.page_size)
            .offset(filters.offset)
        )

        return Result.ok(
            PaginatedResponse.ok(
                data=[ExpenseResponseDto.model_validate(e) for e in rows.scalars().all()],
                page=filters.page,
                page_size=filters.page_size,
                total=total,
            )
        )

    # ── Get single ────────────────────────────────────────────────────────────

    async def get(self, user_id: uuid.UUID, expense_id: uuid.UUID) -> Result[ExpenseResponseDto]:
        expense = await self._load(expense_id, user_id)
        if expense is None:
            return Result.fail("Expense not found.", error_code="NOT_FOUND", status_code=404)
        return Result.ok(ExpenseResponseDto.model_validate(expense))

    # ── Create manual ─────────────────────────────────────────────────────────

    async def create_manual(
        self,
        user_id: uuid.UUID,
        dto: CreateManualExpenseDto,
        receipt: Optional[UploadFile] = None,
    ) -> Result[ExpenseResponseDto]:
        categories = await self._fetch_categories(dto.category_ids)
        if len(categories) != len(dto.category_ids):
            return Result.fail("One or more category IDs are invalid.", error_code="INVALID_CATEGORY", status_code=400)

    
        source = "manual"
        extra_data: Optional[dict] = None
        file_record: Optional[File] = None
        if receipt is not None:
            image_bytes = await receipt.read()
            content_type = receipt.content_type or "image/jpeg"

            try:
                ocr_result = await self._ocr.parse_receipt(image_bytes, content_type)
            except ValueError as exc:
                return Result.fail(str(exc), error_code="INVALID_IMAGE", status_code=400)
            except RuntimeError as exc:
                return Result.fail(str(exc), error_code="OCR_FAILED", status_code=502)

            if not _receipt_amount_matches(dto.amount, ocr_result.total):
                return Result.fail(
                    f"The receipt shows {ocr_result.total}, which doesn't match the "
                    f"{dto.amount} you entered. Please correct the amount or upload the matching receipt.",
                    error_code="RECEIPT_AMOUNT_MISMATCH",
                    status_code=422,
                )

            file_name = f"{uuid.uuid4()}.{content_type.split('/')[-1]}"
            folder = f"receipts/{user_id}"
            await self._storage.upload(folder, file_name, image_bytes, content_type)

            file_record = File(
                folder=folder, file_name=file_name, content_type=content_type, size_bytes=len(image_bytes)
            )
            self._db.add(file_record)
            await self._db.flush()

            source = "receipt"
            extra_data = {"confidence": ocr_result.confidence, "ai_verified": True}

        expense = Expense(
            user_id=user_id,
            amount=dto.amount,
            description=dto.description,
            expense_date=dto.expense_date,
            currency=dto.currency,
            type=ExpenseType.DEBIT.value,
            direction=ExpenseDirection.OUTBOUND.value,
            status=ExpenseStatus.COMPLETED.value,
            source=source,
            file_id=file_record.id if file_record else None,
            extra_data=extra_data,
            created_by=user_id,
            updated_by=user_id,
        )
        expense.categories = categories
        self._db.add(expense)
        await self._db.flush()

        for item_dto in dto.items:
            self._db.add(ExpenseItem(
                expense_id=expense.id,
                name=item_dto.name,
                quantity=item_dto.quantity,
                unit_price=item_dto.unit_price,
                total_price=item_dto.unit_price * item_dto.quantity,
                category_id=item_dto.category_id,
                created_by=user_id,
                updated_by=user_id,
            ))

        await self._db.commit()
        expense = await self._load(expense.id, user_id)  # type: ignore[assignment]
        dto = ExpenseResponseDto.model_validate(expense)
        dto.clara_insight = await self._clara.post_expense_insight(user_id, expense)  # type: ignore[union-attr]
        return Result.ok(dto, status_code=201)

    # ── Create from receipt (OCR) ─────────────────────────────────────────────

    async def create_from_receipt(
        self, user_id: uuid.UUID, image: UploadFile
    ) -> Result[ExpenseResponseDto]:
        image_bytes = await image.read()
        content_type = image.content_type or "image/jpeg"

        try:
            ocr_result = await self._ocr.parse_receipt(image_bytes, content_type)
        except ValueError as exc:
            return Result.fail(str(exc), error_code="INVALID_IMAGE", status_code=400)
        except RuntimeError as exc:
            return Result.fail(str(exc), error_code="OCR_FAILED", status_code=502)

        file_name = f"{uuid.uuid4()}.{content_type.split('/')[-1]}"
        folder = f"receipts/{user_id}"
        await self._storage.upload(folder, file_name, image_bytes, content_type)

        file_record = File(
            folder=folder,
            file_name=file_name,
            content_type=content_type,
            size_bytes=len(image_bytes),
        )
        self._db.add(file_record)
        await self._db.flush()

        expense = Expense(
            user_id=user_id,
            amount=ocr_result.total,
            description=ocr_result.merchant,
            expense_date=datetime.utcnow(),
            currency=ocr_result.currency,
            type=ExpenseType.DEBIT.value,
            direction=ExpenseDirection.OUTBOUND.value,
            status=ExpenseStatus.COMPLETED.value,
            source="receipt",
            file_id=file_record.id,
            created_by=user_id,
            updated_by=user_id,
            extra_data={
                "confidence": ocr_result.confidence,
                "tax": str(ocr_result.tax) if ocr_result.tax is not None else None,
                "discount": str(ocr_result.discount) if ocr_result.discount is not None else None,
                "low_confidence": ocr_result.confidence < _RECEIPT_LOW_CONFIDENCE,
            },
        )
        self._db.add(expense)
        await self._db.flush()

        for ocr_item in ocr_result.items:
            self._db.add(ExpenseItem(
                expense_id=expense.id,
                name=ocr_item.name,
                quantity=ocr_item.quantity,
                unit_price=ocr_item.unit_price,
                total_price=ocr_item.unit_price * ocr_item.quantity,
                created_by=user_id,
                updated_by=user_id,
            ))

        await self._db.commit()
        expense = await self._load(expense.id, user_id)  # type: ignore[assignment]
        return Result.ok(ExpenseResponseDto.model_validate(expense), status_code=201)  # type: ignore[arg-type]

    # ── Update ────────────────────────────────────────────────────────────────

    async def update(
        self,
        user_id: uuid.UUID,
        expense_id: uuid.UUID,
        dto: UpdateExpenseDto,
        receipt: Optional[UploadFile] = None,
    ) -> Result[ExpenseResponseDto]:
        expense = await self._load(expense_id, user_id)
        if expense is None:
            return Result.fail("Expense not found.", error_code="NOT_FOUND", status_code=404)

        if receipt is not None:
            # Verify against the new amount if one's being set in this same
            # call, otherwise against whatever the expense is currently
            # recorded at — attaching proof shouldn't require also retyping
            # the amount.
            claimed_amount = dto.amount if dto.amount is not None else Decimal(str(expense.amount))

            image_bytes = await receipt.read()
            content_type = receipt.content_type or "image/jpeg"

            try:
                ocr_result = await self._ocr.parse_receipt(image_bytes, content_type)
            except ValueError as exc:
                return Result.fail(str(exc), error_code="INVALID_IMAGE", status_code=400)
            except RuntimeError as exc:
                return Result.fail(str(exc), error_code="OCR_FAILED", status_code=502)

            if not _receipt_amount_matches(claimed_amount, ocr_result.total):
                return Result.fail(
                    f"The receipt shows {ocr_result.total}, which doesn't match the "
                    f"{claimed_amount} on this expense. Please correct the amount or upload the matching receipt.",
                    error_code="RECEIPT_AMOUNT_MISMATCH",
                    status_code=422,
                )

            file_name = f"{uuid.uuid4()}.{content_type.split('/')[-1]}"
            folder = f"receipts/{user_id}"
            await self._storage.upload(folder, file_name, image_bytes, content_type)

            file_record = File(
                folder=folder, file_name=file_name, content_type=content_type, size_bytes=len(image_bytes)
            )
            self._db.add(file_record)
            await self._db.flush()

            expense.file_id = file_record.id
            expense.source = "receipt"
            expense.extra_data = {
                **(expense.extra_data or {}),
                "confidence": ocr_result.confidence,
                "ai_verified": True,
            }

        if dto.amount is not None:
            expense.amount = dto.amount
        if dto.description is not None:
            expense.description = dto.description
        if dto.expense_date is not None:
            expense.expense_date = dto.expense_date
        if dto.currency is not None:
            expense.currency = dto.currency
        if dto.status is not None:
            expense.status = dto.status.value
        if dto.category_ids is not None:
            categories = await self._fetch_categories(dto.category_ids)
            if len(categories) != len(dto.category_ids):
                return Result.fail(
                    "One or more category IDs are invalid.",
                    error_code="INVALID_CATEGORY",
                    status_code=400,
                )
            expense.categories = categories

        if dto.items is not None:
            items_by_id = {item.id: item for item in expense.items}
            for item_dto in dto.items:
                item = items_by_id.get(item_dto.id)
                if item is None:
                    return Result.fail(
                        f"Item {item_dto.id} not found on this expense.",
                        error_code="NOT_FOUND",
                        status_code=404,
                    )

                if item_dto.category_id is not None:
                    categories = await self._fetch_categories([item_dto.category_id])
                    if not categories:
                        return Result.fail(
                            "Invalid category ID.", error_code="INVALID_CATEGORY", status_code=400
                        )
                    item.category_id = item_dto.category_id

                if item_dto.name is not None:
                    item.name = item_dto.name
                if item_dto.quantity is not None:
                    item.quantity = item_dto.quantity
                if item_dto.unit_price is not None:
                    item.unit_price = item_dto.unit_price
                item.total_price = item.unit_price * item.quantity
                item.updated_by = user_id

        expense.updated_by = user_id
        await self._db.commit()
        expense = await self._load(expense_id, user_id)  # type: ignore[assignment]
        return Result.ok(ExpenseResponseDto.model_validate(expense))  # type: ignore[arg-type]

    # ── Soft delete ───────────────────────────────────────────────────────────

    async def delete(self, user_id: uuid.UUID, expense_id: uuid.UUID) -> Result[dict]:
        expense = await self._load(expense_id, user_id)
        if expense is None:
            return Result.fail("Expense not found.", error_code="NOT_FOUND", status_code=404)

        expense.deleted_at = datetime.utcnow()
        expense.updated_by = user_id
        await self._db.commit()
        return Result.ok({"message": "Expense deleted."})

    # ── Summary ───────────────────────────────────────────────────────────────

    async def get_summary(
        self,
        user_id: uuid.UUID,
        year: Optional[int],
        month: Optional[int],
    ) -> Result[ExpenseSummaryDto]:
        today = date.today()
        target_year = year or today.year
        target_month = month or today.month

        month_start, month_end = _month_bounds(target_year, target_month)

        # ── Current month totals ──────────────────────────────────────────
        total_expense = await self._sum_expenses(user_id, month_start, month_end)

        # ── Previous month for MoM change ────────────────────────────────
        prev_year, prev_month = (target_year, target_month - 1) if target_month > 1 else (target_year - 1, 12)
        prev_start, prev_end = _month_bounds(prev_year, prev_month)
        prev_expense = await self._sum_expenses(user_id, prev_start, prev_end)

        if prev_expense > 0:
            mom_change_pct = abs((total_expense - prev_expense) / prev_expense * 100)
            mom_direction: Optional[str] = "less" if total_expense < prev_expense else ("more" if total_expense > prev_expense else "same")
        else:
            mom_change_pct = None
            mom_direction = None

        # ── Category breakdown ────────────────────────────────────────────
        cat_rows = await self._db.execute(
            select(
                Category.name,
                func.sum(Expense.amount).label("total"),
                func.count(Expense.id).label("tx_count"),
            )
            .join(expense_categories, expense_categories.c.category_id == Category.id)
            .join(Expense, Expense.id == expense_categories.c.expense_id)
            .where(
                Expense.user_id == user_id,
                Expense.deleted_at.is_(None),
                Expense.expense_date >= month_start,
                Expense.expense_date <= month_end,
            )
            .group_by(Category.name)
            .order_by(func.sum(Expense.amount).desc())
        )
        categories = [
            CategoryExpenseSummaryDto(
                name=row.name,
                amount=float(row.total),
                transaction_count=row.tx_count,
                pct_of_total=(float(row.total) / total_expense * 100) if total_expense > 0 else 0.0,
            )
            for row in cat_rows.all()
        ]

        # ── 6-month trend window (3 before + current + 2 ahead) ──────────
        trend_months = _month_window(target_year, target_month, before=3, ahead=2)
        monthly_trend: list[MonthlyTrendPointDto] = []
        for ty, tm in trend_months:
            ts, te = _month_bounds(ty, tm)
            is_future = date(ty, tm, 1) > today
            total = None if is_future else await self._sum_expenses(user_id, ts, te)
            monthly_trend.append(
                MonthlyTrendPointDto(month=month_abbr[tm], year=ty, total=total)
            )

        # ── Income/expense trend ──────────────────────────────────────────
        income_trend: list[IncomeExpenseTrendPointDto] = []
        for ty, tm in trend_months:
            ts, te = _month_bounds(ty, tm)
            exp_total = 0.0 if date(ty, tm, 1) > today else await self._sum_expenses(user_id, ts, te)
            inc_total = await self._monthly_income_for(user_id, ty, tm)
            income_trend.append(
                IncomeExpenseTrendPointDto(month=month_abbr[tm], year=ty, income=inc_total, expense=exp_total)
            )

        monthly_income = await self._monthly_income_for(user_id, target_year, target_month)

        return Result.ok(
            ExpenseSummaryDto(
                month_label=f"{datetime(target_year, target_month, 1).strftime('%B')} {target_year}",
                total_expense=total_expense,
                mom_change_pct=mom_change_pct,
                mom_direction=mom_direction,
                categories=categories,
                monthly_trend=monthly_trend,
                income_expense_trend=income_trend,
                monthly_income=monthly_income,
            )
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _sum_expenses(self, user_id: uuid.UUID, start: datetime, end: datetime) -> float:
        row = await self._db.execute(
            select(func.sum(Expense.amount)).where(
                Expense.user_id == user_id,
                Expense.deleted_at.is_(None),
                Expense.expense_date >= start,
                Expense.expense_date <= end,
            )
        )
        return float(row.scalar_one() or 0)

    async def _monthly_income_for(self, user_id: uuid.UUID, year: int, month: int) -> float:
        month_start_d = date(year, month, 1)
        rows = await self._db.execute(
            select(Income.amount, Income.reoccurrence, Income.start_date, Income.end_date).where(
                Income.user_id == user_id,
                Income.start_date <= date(year, month, 28),  # active by end of month
            )
        )
        total = 0.0
        _multipliers = {
            IncomeReoccurrence.DAILY: 30,
            IncomeReoccurrence.WEEKLY: 4,
            IncomeReoccurrence.MONTHLY: 1,
        }
        for amount, reoccurrence, start, end in rows.all():
            rec = IncomeReoccurrence(reoccurrence)
            if rec == IncomeReoccurrence.ONE_TIME:
                if start >= month_start_d and (end is None or end <= date(year, month, 28)):
                    total += float(amount)
            else:
                if end is None or end >= month_start_d:
                    total += float(amount) * _multipliers.get(rec, 1)
        return total

    async def _load(self, expense_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Expense]:
        result = await self._db.execute(
            select(Expense)
            .where(
                Expense.id == expense_id,
                Expense.user_id == user_id,
                Expense.deleted_at.is_(None),
            )
            .options(
                selectinload(Expense.categories),
                selectinload(Expense.items),
                selectinload(Expense.file),
            )
        )
        return result.scalar_one_or_none()

    async def _fetch_categories(self, ids: list[uuid.UUID]) -> list[Category]:
        if not ids:
            return []
        result = await self._db.execute(select(Category).where(Category.id.in_(ids)))
        return list(result.scalars().all())


def get_expense_service(
    db: AsyncSession = Depends(get_db),
    clara: ClaraService = Depends(get_clara_service),
) -> ExpenseService:
    return ExpenseService(db, clara)


_RECEIPT_AMOUNT_TOLERANCE_PCT = Decimal("0.01")  # 1% allowed drift (rounding, OCR noise)
_RECEIPT_AMOUNT_TOLERANCE_MIN = Decimal("0.01")  # minimum absolute tolerance


def _receipt_amount_matches(claimed: Decimal, detected: Decimal) -> bool:
    tolerance = max(_RECEIPT_AMOUNT_TOLERANCE_MIN, claimed * _RECEIPT_AMOUNT_TOLERANCE_PCT)
    return abs(claimed - detected) <= tolerance


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    return (
        datetime(year, month, 1, 0, 0, 0),
        datetime(year, month, last_day, 23, 59, 59),
    )


def _month_window(year: int, month: int, before: int, ahead: int) -> list[tuple[int, int]]:
    result = []
    for offset in range(-before, ahead + 1):
        m = month + offset
        y = year
        while m < 1:
            m += 12
            y -= 1
        while m > 12:
            m -= 12
            y += 1
        result.append((y, m))
    return result
