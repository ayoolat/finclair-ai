from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.common.middleware import ErrorHandlerMiddleware, validation_exception_handler
from app.core.config import settings
from app.module.auth.router import router as auth_router
from app.module.user.router import router as user_router

app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Middleware
app.add_middleware(ErrorHandlerMiddleware)

# Exception handlers
app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]

# Routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(user_router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
