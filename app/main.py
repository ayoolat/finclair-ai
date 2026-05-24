from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.common.middleware import ErrorHandlerMiddleware, validation_exception_handler
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.startup import check_database, check_redis, run_startup_checks
from app.module.auth.router import router as auth_router
from app.module.email.router import router as email_router
from app.module.user.router import router as user_router

configure_logging(debug=settings.debug)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await run_startup_checks()
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "Finclair AI — personal finance API.\n\n"
        "**Auth flow:** `register` → verify email OTP → `login` → use `access_token` (15 min) "
        "→ `refresh` with `refresh_token` (30 days) when expired.\n\n"
        "All protected endpoints require `Authorization: Bearer <access_token>`."
    ),
    debug=settings.debug,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(ErrorHandlerMiddleware)
app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]

app.include_router(auth_router, prefix="/api/v1")
app.include_router(user_router, prefix="/api/v1")
app.include_router(email_router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health() -> dict:
    db_ok = await check_database()
    redis_ok = check_redis()
    status = "ok" if db_ok and redis_ok else "degraded"
    return {
        "status": status,
        "database": "ok" if db_ok else "unreachable",
        "redis": "ok" if redis_ok else "unreachable",
    }
