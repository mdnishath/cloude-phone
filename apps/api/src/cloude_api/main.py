"""ASGI entrypoint. Run via: `uvicorn cloude_api.main:app`."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from cloude_api.api.router import api_v1
from cloude_api.config import get_settings
from cloude_api.core.deps import close_redis
from cloude_api.core.rate_limit import limiter
from cloude_api.schemas.error import ErrorBody, ErrorEnvelope
from cloude_api.ws.status import router as ws_status_router

log = logging.getLogger("cloude.api")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    log.info("api startup environment=%s", get_settings().environment)
    yield
    await close_redis()
    log.info("api shutdown")


app = FastAPI(
    title="Cloude Phone API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

settings = get_settings()
if settings.cors_origins_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.state.limiter = limiter
app.include_router(api_v1)
app.include_router(ws_status_router)


def _envelope(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return ErrorEnvelope(error=ErrorBody(code=code, message=message, details=details)).model_dump()


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code_map = {
        400: "bad_request",
        401: "unauthorized",
        402: "payment_required",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        410: "gone",
        429: "rate_limited",
        500: "internal_error",
    }
    code = code_map.get(exc.status_code, "error")
    detail_obj = exc.detail if isinstance(exc.detail, dict) else None
    msg = str(exc.detail) if not isinstance(exc.detail, dict) else code
    return JSONResponse(status_code=exc.status_code, content=_envelope(code, msg, detail_obj))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_envelope(
            "validation_error", "request validation failed", {"errors": exc.errors()}
        ),
    )


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content=_envelope("rate_limited", "too many requests", {"limit": str(exc.detail)}),
    )


@app.get("/healthz", tags=["meta"])
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
