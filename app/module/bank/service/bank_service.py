import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.dto.pagination import PageQueryDto
from app.common.enums.expense import ExpenseDirection, ExpenseStatus, ExpenseType
from app.common.enums.notification import NotificationType
from app.common.response import PaginatedResponse, Result
from app.database.session import get_db
from app.module.bank.dto.bank import BankResponseDto, LinkBankDto
from app.module.bank.schema.bank import Bank
from app.module.bank.service.mono_service import MonoService, get_mono_service
from app.module.expense.schema.expense import Expense
from app.module.notification.service.notification_service import NotificationService, get_notification_service
from app.module.paystack_bank.schema.paystack_bank import PaystackBank

logger = logging.getLogger(__name__)


class BankService:
    def __init__(self, db: AsyncSession, mono: MonoService, notifications: NotificationService) -> None:
        self._db = db
        self._mono = mono
        self._notifications = notifications

    # ── List user banks ───────────────────────────────────────────────────────

    async def list_banks(
        self, user_id: uuid.UUID, filters: PageQueryDto
    ) -> Result[PaginatedResponse[BankResponseDto]]:
        base = select(Bank).where(Bank.user_id == user_id, Bank.deleted_at.is_(None))

        total = (await self._db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

        rows = await self._db.execute(base.offset(filters.offset).limit(filters.page_size))
        banks = [BankResponseDto.model_validate(b) for b in rows.scalars().all()]
        return Result.ok(PaginatedResponse.ok(data=banks, page=filters.page, page_size=filters.page_size, total=total))

    # ── List available Paystack banks ─────────────────────────────────────────

    async def list_available_banks(self, filters: PageQueryDto) -> Result[PaginatedResponse[dict]]:
        base = select(PaystackBank).where(PaystackBank.is_active == True)  # noqa: E712

        total = (await self._db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

        rows = await self._db.execute(
            base.order_by(PaystackBank.name).offset(filters.offset).limit(filters.page_size)
        )
        banks = [
            {"id": str(b.id), "name": b.name, "code": b.code, "logo_url": b.logo_url}
            for b in rows.scalars().all()
        ]
        return Result.ok(PaginatedResponse.ok(data=banks, page=filters.page, page_size=filters.page_size, total=total))

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

    # ── Mono webhook events ──────────────────────────────────────────────────

    async def handle_mono_webhook(self, event: str, data: dict) -> Result[dict]:
        if event == "mono.events.account_updated":
            account_id = data.get("account", {}).get("_id") or data.get("id")
            if not account_id:
                logger.warning("Mono webhook %s missing account id", event)
                return Result.ok({"handled": False, "event": event})

            bank = await self._load_bank_by_mono_id(account_id)
            if bank is None:
                logger.warning("Mono webhook %s for unknown account_id=%s", event, account_id)
                return Result.ok({"handled": False, "event": event})

            sync_result = await self.sync_transactions(bank.user_id, bank.id)
            if sync_result.is_err:
                logger.warning(
                    "Mono webhook %s: sync failed for bank_id=%s — %s",
                    event, bank.id, sync_result.error,
                )
                return Result.ok({"handled": False, "event": event})

            logger.info("Mono webhook %s: synced bank_id=%s", event, bank.id)

            synced = sync_result.data["synced"]
            if synced > 0:
                await self._notifications.notify(
                    bank.user_id,
                    NotificationType.BANK_SYNC_COMPLETED,
                    title="Bank sync complete",
                    body=f"{bank.name} synced — {synced} new transaction{'s' if synced != 1 else ''} added.",
                    data={"bank_id": str(bank.id), "synced": synced},
                )

            return Result.ok({"handled": True, "event": event, **sync_result.data})

        logger.info("Mono webhook %s: no handler, acknowledged", event)
        return Result.ok({"handled": False, "event": event})

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
                expense_date=datetime.fromisoformat(tx["date"]) if "date" in tx else datetime.now(timezone.utc),
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

        bank.deleted_at = datetime.now(timezone.utc)
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

    async def _load_bank_by_mono_id(self, mono_account_id: str) -> Optional[Bank]:
        result = await self._db.execute(
            select(Bank).where(
                Bank.mono_account_id == mono_account_id,
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
    notifications: NotificationService = Depends(get_notification_service),
) -> BankService:
    return BankService(db, mono, notifications)
