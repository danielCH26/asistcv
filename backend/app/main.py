"""
FastAPI application main entry point.
"""
import uuid
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1 import health, match, ping
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    configure_logging()
    logger = get_logger("app")
    logger.info("application_startup", environment=get_settings().environment)
    yield
    logger.info("application_shutdown")


app = FastAPI(
    title=get_settings().app_name,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
settings = get_settings()
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

# Include routers
app.include_router(health.router)
app.include_router(ping.router, prefix=settings.api_prefix)
app.include_router(match.router, prefix=settings.api_prefix)
