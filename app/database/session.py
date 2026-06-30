from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

_SSL_MODES = {"require", "verify-ca", "verify-full", "allow", "prefer"}


def _prepare_url(url: str) -> tuple[str, dict]:
    """
    Normalise a postgres URL for asyncpg:
    - Rewrites scheme to postgresql+asyncpg://
    - Strips sslmode query param (psycopg2-only) and converts it to a connect_arg
    Returns (url, connect_args).
    """
    url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    sslmode = params.pop("sslmode", [None])[0]

    connect_args: dict = {}
    if sslmode and sslmode in _SSL_MODES:
        connect_args["ssl"] = "require" if sslmode in {"require", "verify-ca", "verify-full"} else False

    new_query = urlencode({k: v[0] for k, v in params.items()})
    clean_url = urlunparse(parsed._replace(query=new_query))
    return clean_url, connect_args


_db_url, _connect_args = _prepare_url(settings.database_url)

engine = create_async_engine(_db_url, echo=settings.debug, connect_args=_connect_args)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:  # type: ignore[return]
    async with AsyncSessionLocal() as session:
        yield session  # type: ignore[misc]
