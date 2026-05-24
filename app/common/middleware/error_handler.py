import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: object) -> Response:
        try:
            response: Response = await call_next(request)  # type: ignore[operator]
            return response
        except Exception as exc:
            logger.exception("Unhandled exception: %s", exc)
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "message": "An unexpected error occurred.",
                    "error_code": "INTERNAL_SERVER_ERROR",
                },
            )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [
        {
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "message": "Validation failed.",
            "errors": errors,
        },
    )
