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
        raise
    finally:
        await engine.dispose()


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
