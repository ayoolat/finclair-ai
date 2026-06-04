import logging

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.core.config import settings
from app.database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def run_migrations() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    def _upgrade(connection: object) -> None:
        alembic_cfg = Config("alembic.ini")
        alembic_cfg.attributes["connection"] = connection
        command.upgrade(alembic_cfg, "head")

    engine = create_async_engine(settings.database_url)
    try:
        async with engine.connect() as conn:
            await conn.run_sync(_upgrade)
        logger.info("Migrations      ✓  applied")
    except Exception as exc:
        logger.error("Migrations      ✗  FAILED — %s", exc)
    finally:
        await engine.dispose()


async def seed_income_sources() -> None:
    from sqlalchemy import select
    from app.module.income.schema.income_source import IncomeSource

    defaults = ["Salary", "Freelance", "Business", "Investment"]
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(IncomeSource).where(IncomeSource.is_default == True)  # noqa: E712
            )
            existing_names = {row.name for row in result.scalars().all()}
            missing = [name for name in defaults if name not in existing_names]
            if missing:
                for name in missing:
                    session.add(IncomeSource(name=name, user_id=None, is_default=True))
                await session.commit()
                logger.info("Income sources  ✓  seeded (%s)", ", ".join(missing))
            else:
                logger.info("Income sources  ✓  present")
    except Exception as exc:
        logger.error("Income sources  ✗  seed FAILED — %s", exc)


async def seed_financial_goals() -> None:
    from sqlalchemy import select
    from app.module.goal.schema.financial_goal import FinancialGoal

    defaults = [
        {
            "key": "smart_money_saving",
            "name": "Save more money",
            "description": "Help me understand my spending and find simple ways to save more every month.",
            "icon_name": "wallet",
        },
        {
            "key": "track_my_spending",
            "name": "Track My Spending",
            "description": "Help me see where my money goes with quick tracking and easy-to-read summaries.",
            "icon_name": "bar-chart",
        },
        {
            "key": "stick_to_a_budget",
            "name": "Stick to a Budget",
            "description": "Help me set spending limits and warn me before I overspend.",
            "icon_name": "pie-chart",
        },
        {
            "key": "feel_more_in_control",
            "name": "Feel More In Control",
            "description": "Help me feel less stressed about money by giving me a clearer picture of my finances.",
            "icon_name": "briefcase",
        },
    ]
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(FinancialGoal))
            existing_keys = {row.key for row in result.scalars().all()}
            missing = [g for g in defaults if g["key"] not in existing_keys]
            if missing:
                for g in missing:
                    session.add(FinancialGoal(**g))
                await session.commit()
                logger.info("Financial goals  ✓  seeded (%s)", ", ".join(g["key"] for g in missing))
            else:
                logger.info("Financial goals  ✓  present")
    except Exception as exc:
        logger.error("Financial goals  ✗  seed FAILED — %s", exc)


async def seed_categories() -> None:
    from sqlalchemy import select
    from app.module.category.schema.category import Category

    defaults = [
        {"name": "Food", "description": "Groceries, restaurants, and food delivery."},
        {"name": "Transportation", "description": "Fuel, fares, ride-hailing, and vehicle costs."},
        {"name": "Health", "description": "Medical, pharmacy, and wellness expenses."},
        {"name": "Shopping", "description": "Clothing, electronics, and general retail."},
        {"name": "Rent", "description": "Rent, mortgage, and accommodation payments."},
        {"name": "Entertainment", "description": "Streaming, events, hobbies, and leisure."},
        {"name": "Investment", "description": "Stocks, savings, and investment contributions."},
        {"name": "Utilities", "description": "Electricity, water, internet, and phone bills."},
        {"name": "Education", "description": "Tuition, books, and learning materials."},
        {"name": "Other", "description": "Miscellaneous expenses not covered elsewhere."},
    ]
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Category))
            existing_names = {row.name for row in result.scalars().all()}
            missing = [c for c in defaults if c["name"] not in existing_names]
            if missing:
                for c in missing:
                    session.add(Category(**c))
                await session.commit()
                logger.info("Categories      ✓  seeded (%s)", ", ".join(c["name"] for c in missing))
            else:
                logger.info("Categories      ✓  present")
    except Exception as exc:
        logger.error("Categories      ✗  seed FAILED — %s", exc)


async def sync_paystack_banks() -> None:
    import asyncio
    from sqlalchemy import select
    from app.common.clients.paystack_client import get_paystack_client
    from app.module.paystack_bank.schema.paystack_bank import PaystackBank

    try:
        client = get_paystack_client()
        response = await asyncio.to_thread(
            client.get, "/bank", params={"perPage": 200, "country": "nigeria"}
        )
        response.raise_for_status()
        banks_data = response.json().get("data", [])

        async with AsyncSessionLocal() as session:
            existing = await session.execute(select(PaystackBank.paystack_id))
            existing_ids = {row[0] for row in existing.all()}

            new_banks = [b for b in banks_data if b["id"] not in existing_ids]
            for b in new_banks:
                session.add(PaystackBank(
                    paystack_id=b["id"],
                    name=b["name"],
                    code=b["code"],
                    slug=b.get("slug", ""),
                    country=b.get("country", "NG"),
                    currency=b.get("currency", "NGN"),
                    bank_type=b.get("type", "nuban"),
                    is_active=b.get("active", True),
                    logo_url=b.get("logo"),
                ))

            if new_banks:
                await session.commit()
                logger.info("Paystack banks  ✓  synced (%d new)", len(new_banks))
            else:
                logger.info("Paystack banks  ✓  up to date")
    except Exception as exc:
        logger.error("Paystack banks  ✗  sync FAILED — %s", exc)


async def check_database() -> bool:
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        logger.info("Database        ✓  connected  (%s)", _safe_db_url())
        return True
    except Exception as exc:
        logger.error("Database        ✗  FAILED — %s", exc)
        return False


def check_redis() -> bool:
    try:
        from app.common.queue.connection import redis_conn
        redis_conn.ping()
        logger.info("Redis           ✓  connected  (%s)", settings.redis_url)
        return True
    except Exception as exc:
        logger.error("Redis           ✗  FAILED — %s", exc)
        return False


async def run_startup_checks() -> None:
    logger.info("━" * 52)
    logger.info("  %s", settings.app_name)
    logger.info("  debug=%s", settings.debug)
    logger.info("━" * 52)

    await run_migrations()
    await seed_income_sources()
    await seed_financial_goals()
    await seed_categories()
    db_ok = await check_database()
    redis_ok = check_redis()

    if not db_ok:
        logger.warning("Startup check failed: database unreachable. Migrations may not have run.")
    if not redis_ok:
        logger.warning("Startup check failed: Redis unreachable. Email queue will not work.")

    logger.info("━" * 52)


def _safe_db_url() -> str:
    """Return the DB URL with password masked."""
    url = settings.database_url
    try:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        masked = parsed._replace(netloc=parsed.netloc.replace(f":{parsed.password}@", ":***@"))
        return urlunparse(masked)
    except Exception:
        return "<db_url>"
