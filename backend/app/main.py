"""
FastAPI application main entry point.

Usa `create_app()` para que los tests puedan instanciar la app en modo
abierto o protegido sin contaminar el estado global. Los endpoints bajo
`/v1` exigen API key (pass-through cuando `BACKEND_API_KEY` no está
definida). `/health` y `/` quedan exentos; `/docs`, `/redoc` y
`/openapi.json` se deshabilitan en modo protegido para no exponer el
contrato.
"""

import uuid
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.deps import require_role, verify_api_key
from app.api.v1 import (
    analyses,
    audit,
    auth,
    cvs,
    health,
    match,
    ping,
    profiles,
    recruiter_candidates,
    recruiter_consent,
    users,
)
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.services.consent_gate import check_recruiter_consent


def create_app(settings: Settings | None = None) -> FastAPI:
    """Construye la app. `settings=None` usa el singleton cacheado.

    En modo protegido (`backend_api_key` definida) se desactivan docs y
    openapi para no exponer el contrato; en dev/CI (sin key) siguen
    disponibles.
    """
    if settings is None:
        settings = get_settings()

    docs_enabled = not settings.backend_api_key

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
        configure_logging()
        logger = get_logger("app")
        logger.info(
            "application_startup",
            environment=settings.environment,
            auth_enabled=bool(settings.backend_api_key),
        )
        yield
        logger.info("application_shutdown")

    app = FastAPI(
        title=settings.app_name,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request ID middleware
    class RequestIDMiddleware(BaseHTTPMiddleware):
        """Middleware to assign a unique ID to each request."""

        async def dispatch(self, request: Request, call_next):
            request_id = str(uuid.uuid4())
            request.state.request_id = request_id

            logger = get_logger("request")
            logger = logger.bind(request_id=request_id)

            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response

    app.add_middleware(RequestIDMiddleware)

    # Logging middleware
    class LoggingMiddleware(BaseHTTPMiddleware):
        """Middleware to log each request."""

        async def dispatch(self, request: Request, call_next):
            logger = get_logger("request")
            request_id = getattr(request.state, "request_id", "unknown")

            start_time = perf_counter()
            response = await call_next(request)
            duration = perf_counter() - start_time

            logger.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration * 1000, 2),
                request_id=request_id,
            )

            return response

    app.add_middleware(LoggingMiddleware)

    # Root: metadata mínima, exenta de auth.
    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "name": settings.app_name,
            "version": "0.1.0",
            "docs": "/docs" if docs_enabled else "disabled",
        }

    # Routers — /health y / exentos; /auth/register y /auth/login públicos.
    app.include_router(health.router)
    app.include_router(
        auth.router,
        prefix=settings.api_prefix,
    )  # /auth/register and /auth/login are public, others need auth via deps

    # Users endpoints require auth in both modes
    app.include_router(
        users.router,
        prefix=settings.api_prefix,
        dependencies=[Depends(verify_api_key)],
    )

    # These endpoints use optional_auth - they work without auth in open mode
    # but require auth in protected mode (when BACKEND_API_KEY is set)
    from app.api.deps import optional_auth

    app.include_router(
        ping.router,
        prefix=settings.api_prefix,
        dependencies=[Depends(optional_auth)],
    )
    app.include_router(
        match.router,
        prefix=settings.api_prefix,
        dependencies=[Depends(optional_auth)],
    )
    app.include_router(
        analyses.router,
        prefix=settings.api_prefix,
        dependencies=[Depends(optional_auth)],
    )
    app.include_router(
        profiles.router,
        prefix=settings.api_prefix,
        dependencies=[Depends(optional_auth)],
    )
    app.include_router(
        cvs.router,
        prefix=settings.api_prefix,
        dependencies=[Depends(optional_auth)],
    )

    # Audit endpoints are public (no auth required for anonymous funnel)
    app.include_router(
        audit.router,
        prefix=settings.api_prefix,
    )
    # Internal cleanup endpoint (protected by token)
    app.include_router(
        audit.router,
        prefix="",
    )

    # Recruiter consent endpoint (requires recruiter role)
    app.include_router(
        recruiter_consent.router,
        prefix=settings.api_prefix,
        dependencies=[Depends(verify_api_key), Depends(require_role("recruiter"))],
    )

    # Recruiter candidates endpoints (requires recruiter role + consent)
    app.include_router(
        recruiter_candidates.router,
        prefix=settings.api_prefix,
        dependencies=[Depends(verify_api_key), Depends(check_recruiter_consent)],
    )

    # Billing endpoints. /plans is public (conversion funnel — visitors must
    # see pricing before signing up); the other endpoints enforce auth at the
    # endpoint level via Depends(get_current_user).
    from app.api.v1 import billing

    app.include_router(
        billing.router,
        prefix=settings.api_prefix,
    )

    # Stripe webhook endpoint (no auth - uses signature verification)
    from app.api.v1.webhooks import stripe as stripe_webhook

    app.include_router(
        stripe_webhook.router,
        prefix="/api/v1",
        include_in_schema=False,
    )

    return app


app = create_app()
