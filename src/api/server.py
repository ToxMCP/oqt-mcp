import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from src.auth.config import validate_oidc_configuration

# Import configurations and initialize logging first
from src.config.settings import settings
from src.utils import audit
from src.utils.logging import setup_logging

setup_logging()

# Import tool implementations to ensure they register themselves with the registry
import src.tools.implementations.o_qt_qsar_tools
import src.tools.implementations.toolbox_discovery

# Import routers
from src.mcp.router import router as mcp_router

log = logging.getLogger(__name__)

app = FastAPI(
    title="O-QT MCP Server",
    description="Model Context Protocol Server for the OECD QSAR Toolbox. Built for security and interoperability.",
    version="0.1.0",
)

# --- Middleware ---

# CORS (Cross-Origin Resource Sharing)
# CRITICAL: Restrict allow_origins in production to specific MCP Hosts.
if settings.app.ENVIRONMENT == "development":
    origins = ["*"]
else:
    # Update this list for production
    origins = ["https://your.mcp.host.com"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# Security Headers Middleware (Section 2.4)
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    # Implement a strict Content-Security-Policy (CSP) in production
    # response.headers["Content-Security-Policy"] = "default-src 'self'"
    return response


# Audit Logging Middleware (Section 2.3: Immutable Audit Trails)
# Placeholder: In production, this must log to a centralized, tamper-evident system.
@app.middleware("http")
async def audit_log_middleware(request: Request, call_next):
    correlation_id = str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    start = time.perf_counter()

    log.debug(
        "Incoming request",
        extra={
            "cid": correlation_id,
            "method": request.method,
            "path": request.url.path,
        },
    )

    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000

    user_id = getattr(getattr(request.state, "user", None), "id", "anonymous")
    event = {
        "type": "http_request",
        "correlation_id": correlation_id,
        "user_id": user_id,
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "duration_ms": round(duration_ms, 3),
    }
    audit.emit(event)

    response.headers["X-Request-ID"] = correlation_id
    log.debug(
        "Outgoing response",
        extra={"cid": correlation_id, "status": response.status_code},
    )
    return response


# --- Routers ---
app.include_router(mcp_router)


# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "environment": settings.app.ENVIRONMENT,
        "auth_bypassed": settings.security.BYPASS_AUTH,
        "qsar_api_url": settings.qsar.QSAR_TOOLBOX_API_URL,
    }


# Startup event
@app.on_event("startup")
async def startup_event():
    log.info("O-QT MCP Server starting up...")
    if settings.security.BYPASS_AUTH:
        log.warning(
            "WARNING: Authentication bypass (BYPASS_AUTH) is enabled. Do not run in production."
        )
    if settings.qsar.QSAR_TOOLBOX_API_URL.startswith("http://localhost"):
        log.warning(
            f"QSAR Toolbox API URL is set to a local address: {settings.qsar.QSAR_TOOLBOX_API_URL}. Ensure this is accessible from the container/server environment."
        )
    try:
        validate_oidc_configuration()
    except RuntimeError as exc:
        log.error(f"OIDC configuration validation failed: {exc}")
        if not settings.security.BYPASS_AUTH:
            raise


if __name__ == "__main__":
    import uvicorn

    # For local development execution
    uvicorn.run("src.api.server:app", host="0.0.0.0", port=8000, reload=True)
