import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import Depends, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.enums.expense import ExpenseDirection, ExpenseStatus, ExpenseType
from app.common.ocr.factory import get_ocr_provider
from app.common.response import PaginatedResponse, Result
from app.common.storage.factory import get_storage_provider
from app.database.session import get_db
from app.module.category.schema.category import Category
from app.module.expense.dto.expense import (
    CreateManualExpenseDto,
    ExpenseFilterDto,
    ExpenseResponseDto,
    UpdateExpenseDto,
)
from app.module.expense.schema.expense import Expense
from app.module.expense.schema.expense_category import expense_categories
from app.module.expense.schema.expense_item import ExpenseItem
from app.module.file.schema.file import File

_RECEIPT_LOW_CONFIDENCE = 0.5


class ExpenseService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
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
        self, user_id: uuid.UUID, dto: CreateManualExpenseDto
    ) -> Result[ExpenseResponseDto]:
        categories = await self._fetch_categories(dto.category_ids)
        if len(categories) != len(dto.category_ids):
            return Result.fail("One or more category IDs are invalid.", error_code="INVALID_CATEGORY", status_code=400)

        expense = Expense(
            user_id=user_id,
            amount=dto.amount,
            description=dto.description,
            expense_date=dto.expense_date,
            currency=dto.currency,
            type=ExpenseType.DEBIT.value,
            direction=ExpenseDirection.OUTBOUND.value,
            status=ExpenseStatus.COMPLETED.value,
            source="manual",
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
        return Result.ok(ExpenseResponseDto.model_validate(expense), status_code=201)  # type: ignore[arg-type]

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
        self, user_id: uuid.UUID, expense_id: uuid.UUID, dto: UpdateExpenseDto
    ) -> Result[ExpenseResponseDto]:
        expense = await self._load(expense_id, user_id)
        if expense is None:
            return Result.fail("Expense not found.", error_code="NOT_FOUND", status_code=404)

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

    # ── Helpers ───────────────────────────────────────────────────────────────

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


def get_expense_service(db: AsyncSession = Depends(get_db)) -> ExpenseService:
    return ExpenseService(db)
