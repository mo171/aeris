"""Global exception handlers for the FastAPI serving layer.

Maps domain failures into the wire contract:
- AerisError subclasses -> ApiErrorPayload with exact status & code.
- RequestValidationError -> ApiErrorPayload with code VALIDATION_FAILED.
- Uncaught exceptions -> ApiErrorPayload with code INTERNAL_ERROR.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.constants.errors import ErrorCode
from app.lib.exceptions import AerisError, to_error_payload

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach global exception handlers to the FastAPI application instance."""

    @app.exception_handler(AerisError)
    async def aeris_error_handler(request: Request, exc: AerisError) -> JSONResponse:
        logger.warning(
            "Domain error handled",
            extra={
                "code": exc.code.value,
                "status": exc.status,
                "error_message": exc.message,
                "path": request.url.path,
            },
        )
        return JSONResponse(
            status_code=exc.status,
            content=to_error_payload(exc),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.warning(
            "Request validation failed",
            extra={
                "path": request.url.path,
                "errors": exc.errors(),
            },
        )
        return JSONResponse(
            status_code=422,
            content={
                "message": "The request payload failed validation.",
                "code": ErrorCode.VALIDATION_FAILED.value,
                "status": 422,
                "details": {"errors": exc.errors()},
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled server error",
            extra={
                "path": request.url.path,
                "error": str(exc),
            },
        )
        return JSONResponse(
            status_code=500,
            content={
                "message": "An internal server error occurred.",
                "code": ErrorCode.INTERNAL_ERROR.value,
                "status": 500,
            },
        )
