import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.database.session import Base

# All models must be imported so Alembic detects schema changes
from app.module.user.schema.user import User  # noqa: F401
from app.module.user.schema.user_goal import UserGoal  # noqa: F401
from app.module.bank.schema.bank import Bank  # noqa: F401
from app.module.income.schema.income import Income  # noqa: F401
from app.module.category.schema.category import Category  # noqa: F401
from app.module.expense.schema.expense_category import expense_categories  # noqa: F401
from app.module.expense.schema.expense import Expense  # noqa: F401
from app.module.expense.schema.expense_item import ExpenseItem  # noqa: F401
from app.module.budget.schema.budget import Budget  # noqa: F401
from app.module.auth.schema.otp_token import OtpToken  # noqa: F401
from app.module.auth.schema.session import Session  # noqa: F401
from app.module.income.schema.income_source import IncomeSource  # noqa: F401
from app.module.friends.schema.friendship import Friendship  # noqa: F401
from app.module.groups.schema.group import Group  # noqa: F401
from app.module.groups.schema.group_member import GroupMember  # noqa: F401
from app.module.groups.schema.group_savings_entry import GroupSavingsEntry  # noqa: F401
from app.module.groups.schema.group_message import GroupMessage  # noqa: F401
from app.module.marketing.schema.newsletter import NewsletterSubscriber  # noqa: F401
from app.module.marketing.schema.waitlist import WaitlistEntry  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: object) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)  # type: ignore[arg-type]
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    from app.database.session import _prepare_url
    db_url, connect_args = _prepare_url(settings.database_url)
    engine = create_async_engine(db_url, connect_args=connect_args)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    # When called programmatically (e.g. on startup), a live connection is
    # injected via config.attributes so we don't create a second engine.
    injected_conn = config.attributes.get("connection")
    if injected_conn is not None:
        do_run_migrations(injected_conn)
    else:
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
