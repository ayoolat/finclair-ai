import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.enums.expense import ExpenseDirection, ExpenseStatus, ExpenseType
from app.common.response import Result
from app.database.session import get_db
from app.module.bank.dto.bank import BankResponseDto, LinkBankDto
from app.module.bank.schema.bank import Bank
from app.module.bank.service.mono_service import MonoService, get_mono_service
from app.module.expense.schema.expense import Expense
from app.module.paystack_bank.schema.paystack_bank import PaystackBank


class BankService:
    def __init__(self, db: AsyncSession, mono: MonoService) -> None:
        self._db = db
        self._mono = mono

    # ── List user banks ───────────────────────────────────────────────────────

    async def list_banks(self, user_id: uuid.UUID) -> Result[list[BankResponseDto]]:
        rows = await self._db.execute(
            select(Bank).where(Bank.user_id == user_id, Bank.deleted_at.is_(None))
        )
        return Result.ok([BankResponseDto.model_validate(b) for b in rows.scalars().all()])

    # ── List available Paystack banks ─────────────────────────────────────────

    async def list_available_banks(self) -> Result[list[dict]]:
        rows = await self._db.execute(
            select(PaystackBank).where(PaystackBank.is_active == True)  # noqa: E712
            .order_by(PaystackBank.name)
        )
        banks = [
            {"id": str(b.id), "name": b.name, "code": b.code, "logo_url": b.logo_url}
            for b in rows.scalars().all()
        ]
        return Result.ok(banks)

    # ── Link bank via Mono ────────────────────────────────────────────────────

    async def link_bank(self, user_id: uuid.UUID, dto: LinkBankDto) -> Result[BankResponseDto]:
        account_id, mono_error = await self._mono.exchange_code(dto.code)
        if account_id is None:
            return Result.fail(
                mono_error or "Failed to link bank account. Invalid or expired code.",
                error_code="MONO_LINK_FAILED",
                status_code=400,
            )

        account_details = await self._mono.get_account(account_id)
        if account_details is None:
            return Result.fail(
                "Failed to fetch bank account details.",
                error_code="MONO_FETCH_FAILED",
                status_code=502,
            )

        institution = account_details.get("institution", {})
        bank = Bank(
            user_id=user_id,
            name=institution.get("name", "Unknown Bank"),
            account_number=account_details.get("account_number", ""),
            mono_account_id=account_id,
            mono_code=dto.code,
            created_by=user_id,
            updated_by=user_id,
        )
        self._db.add(bank)
        await self._db.commit()
        await self._db.refresh(bank)
        return Result.ok(BankResponseDto.model_validate(bank), status_code=201)

    # ── Balance ───────────────────────────────────────────────────────────────

    async def get_balance(self, user_id: uuid.UUID, bank_id: uuid.UUID) -> Result[dict]:
        bank = await self._load_bank(bank_id, user_id)
        if bank is None:
            return Result.fail("Bank not found.", error_code="NOT_FOUND", status_code=404)
        if bank.mono_account_id is None:
            return Result.fail("Bank not linked to Mono.", error_code="NOT_LINKED", status_code=400)

        data = await self._mono.get_balance(bank.mono_account_id)
        if data is None:
            return Result.fail("Failed to fetch balance.", error_code="MONO_ERROR", status_code=502)

        return Result.ok({
            "bank_id": str(bank_id),
            "bank_name": bank.name,
            "account_number": bank.account_number,
            "balance": data["balance"],
            "currency": data["currency"],
        })

    # ── Sync transactions from Mono (from link time) ──────────────────────────

    async def sync_transactions(
        self, user_id: uuid.UUID, bank_id: uuid.UUID
    ) -> Result[dict]:
        bank = await self._load_bank(bank_id, user_id)
        if bank is None:
            return Result.fail("Bank not found.", error_code="NOT_FOUND", status_code=404)
        if bank.mono_account_id is None:
            return Result.fail("Bank account not linked to Mono.", error_code="NOT_LINKED", status_code=400)

        # Fetch transactions from the time the bank was linked
        linked_since = bank.created_at.strftime("%Y-%m-%d")
        transactions = await self._mono.get_transactions(bank.mono_account_id, since=linked_since)
        created = 0

        for tx in transactions:
            mono_id = tx.get("_id", "")
            if mono_id and await self._transaction_exists(user_id, mono_id):
                continue

            amount = Decimal(str(abs(tx.get("amount", 0))))
            tx_type = tx.get("type", "debit").lower()
            direction = ExpenseDirection.OUTBOUND.value if tx_type == "debit" else ExpenseDirection.INBOUND.value
            expense_type = ExpenseType.DEBIT.value if tx_type == "debit" else ExpenseType.CREDIT.value

            expense = Expense(
                user_id=user_id,
                amount=amount,
                description=tx.get("narration"),
                expense_date=datetime.fromisoformat(tx["date"]) if "date" in tx else datetime.utcnow(),
                currency=tx.get("currency", "NGN"),
                type=expense_type,
                direction=direction,
                status=ExpenseStatus.COMPLETED.value,
                source="bank_sync",
                created_by=user_id,
                updated_by=user_id,
                extra_data={"mono_id": mono_id, "bank_id": str(bank_id)},
            )
            self._db.add(expense)
            created += 1

        await self._db.commit()
        return Result.ok({"synced": created, "bank_id": str(bank_id)})

    # ── Disconnect bank ───────────────────────────────────────────────────────

    async def disconnect_bank(self, user_id: uuid.UUID, bank_id: uuid.UUID) -> Result[dict]:
        bank = await self._load_bank(bank_id, user_id)
        if bank is None:
            return Result.fail("Bank not found.", error_code="NOT_FOUND", status_code=404)

        bank.deleted_at = datetime.utcnow()
        bank.updated_by = user_id
        await self._db.commit()
        return Result.ok({"message": "Bank disconnected."})

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _load_bank(self, bank_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Bank]:
        result = await self._db.execute(
            select(Bank).where(
                Bank.id == bank_id,
                Bank.user_id == user_id,
                Bank.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def _transaction_exists(self, user_id: uuid.UUID, mono_id: str) -> bool:
        result = await self._db.execute(
            select(Expense.id).where(
                Expense.user_id == user_id,
                Expense.extra_data["mono_id"].astext == mono_id,
                Expense.deleted_at.is_(None),
            )
        )
        return result.first() is not None


def get_bank_service(
    db: AsyncSession = Depends(get_db),
    mono: MonoService = Depends(get_mono_service),
) -> BankService:
    return BankService(db, mono)
