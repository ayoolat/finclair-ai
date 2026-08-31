from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.common.middleware import ErrorHandlerMiddleware, validation_exception_handler
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.scheduler import schedule_daily, schedule_daily_at, schedule_every_minutes
from app.core.startup import check_database, check_redis, run_startup_checks, sync_paystack_banks
from app.module.auth.router import router as auth_router
from app.module.bank.router import router as bank_router
from app.module.budget.router import router as budget_router
from app.module.budget.service.budget_alert_service import check_budget_health, check_no_spend_weekend
from app.module.challenge.router import router as challenge_router
from app.module.challenge.service.reminder_jobs import send_friday_savings_reminders
from app.module.challenge.service.tracking_jobs import (
    check_budget_category_challenges,
    check_no_spend_challenges,
)
from app.module.insight.router import router as insight_router
from app.module.category.router import router as category_router
from app.module.clara.router import router as clara_router
from app.module.email.router import router as email_router
from app.module.expense.router import router as expense_router
from app.module.expense.service.daily_notification_jobs import (
    dispatch_evening_spending_checks,
    send_daily_ai_tips,
    send_midday_spending_checks,
)
from app.module.friends.router import router as friends_router
from app.module.goal.router import router as goal_router
from app.module.groups.router import router as groups_router
from app.module.income.router import router as income_router
from app.module.marketing.router import router as marketing_router
from app.module.notification.router import router as notification_router
from app.module.score.router import router as score_router
from app.module.subscription.router import router as subscription_router
from app.module.subscription.service.billing_job import process_subscription_billing
from app.module.user.router import router as user_router
from app.module.wrapped.router import router as wrapped_router

configure_logging(debug=settings.debug)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await run_startup_checks()
    schedule_daily("sync_paystack_banks", sync_paystack_banks)
    schedule_daily("process_subscription_billing", process_subscription_billing)
    schedule_daily("send_friday_savings_reminders", send_friday_savings_reminders)
    schedule_daily("check_no_spend_weekend", check_no_spend_weekend)
    schedule_daily("check_budget_health", check_budget_health)
    schedule_daily("check_no_spend_challenges", check_no_spend_challenges)
    schedule_daily("check_budget_category_challenges", check_budget_category_challenges)
    schedule_daily_at("send_daily_ai_tips", hour=9, minute=0, task_fn=send_daily_ai_tips)
    schedule_daily_at("send_midday_spending_checks", hour=12, minute=0, task_fn=send_midday_spending_checks)
    schedule_every_minutes("dispatch_evening_spending_checks", 15, dispatch_evening_spending_checks)
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
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
app.include_router(friends_router, prefix="/api/v1")
app.include_router(groups_router, prefix="/api/v1")
app.include_router(marketing_router, prefix="/api/v1")
app.include_router(clara_router, prefix="/api/v1")
app.include_router(subscription_router, prefix="/api/v1")
app.include_router(wrapped_router, prefix="/api/v1")
app.include_router(challenge_router, prefix="/api/v1")
app.include_router(notification_router, prefix="/api/v1")
app.include_router(score_router, prefix="/api/v1")


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
