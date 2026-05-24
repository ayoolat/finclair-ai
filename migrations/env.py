import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.database.session import Base

# All models must be imported here so Alembic can detect schema changes
from app.module.user.schema.user import User  # noqa: F401
from app.module.bank.schema.bank import Bank  # noqa: F401
from app.module.income.schema.income import Income  # noqa: F401
from app.module.category.schema.category import Category  # noqa: F401
from app.module.expense.schema.expense_category import expense_categories  # noqa: F401
from app.module.expense.schema.expense import Expense  # noqa: F401
from app.module.expense.schema.expense_item import ExpenseItem  # noqa: F401
from app.module.budget.schema.budget import Budget  # noqa: F401

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
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
