from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.common.middleware import ErrorHandlerMiddleware, validation_exception_handler
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.scheduler import schedule_daily
from app.core.startup import check_database, check_redis, run_startup_checks, sync_paystack_banks
from app.module.auth.router import router as auth_router
from app.module.bank.router import router as bank_router
from app.module.budget.router import router as budget_router
from app.module.insight.router import router as insight_router
from app.module.category.router import router as category_router
from app.module.email.router import router as email_router
from app.module.expense.router import router as expense_router
from app.module.goal.router import router as goal_router
from app.module.income.router import router as income_router
from app.module.user.router import router as user_router

configure_logging(debug=settings.debug)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await run_startup_checks()
    schedule_daily("sync_paystack_banks", sync_paystack_banks)
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
app.include_router(income_router, prefix="/api/v1")
app.include_router(goal_router, prefix="/api/v1")
app.include_router(category_router, prefix="/api/v1")
app.include_router(expense_router, prefix="/api/v1")
app.include_router(bank_router, prefix="/api/v1")
app.include_router(budget_router, prefix="/api/v1")
app.include_router(insight_router, prefix="/api/v1")


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
