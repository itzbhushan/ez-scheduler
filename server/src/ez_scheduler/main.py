#!/usr/bin/env python3
"""EZ Scheduler - Combined MCP and Web Server"""

import uvicorn
from authlib.integrations.starlette_client import OAuth
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastmcp import FastMCP
from starlette.middleware.sessions import SessionMiddleware
from starlette_csrf.middleware import CSRFMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from ez_scheduler.config import config
from ez_scheduler.logging_config import get_logger, setup_logging
from ez_scheduler.routers import publishing
from ez_scheduler.routers.docs import docs_router, set_app_instance
from ez_scheduler.routers.gpt_actions import router as gpt_router
from ez_scheduler.routers.health import health
from ez_scheduler.routers.legal import router as legal_router
from ez_scheduler.routers.mcp_server import mcp_app
from ez_scheduler.routers.oauth import router as oauth_router
from ez_scheduler.routers.registration import router as registration_router

# Configure logging (INFO -> stdout, WARNING/ERROR -> stderr)
setup_logging()
logger = get_logger(__name__)


# Create FastAPI app
app = FastAPI(
    title="EZ Scheduler",
    description="Signup Form Generation and Management API - Create signup forms via conversational AI and handle public registrations",
    version="1.0.0",
    contact={
        "name": "EZ Scheduler API Support",
        "email": "support@ez-scheduler.com",
    },
    license_info={
        "name": "MIT",
    },
    lifespan=mcp_app.lifespan,
    docs_url=None,  # Disable default docs
    redoc_url=None,  # Disable default redoc
)

# Trust proxy headers (Railway, etc. terminate HTTPS and forward via HTTP)
# This ensures request.url.scheme reflects the original HTTPS protocol
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# Add session middleware (required for Auth0 web flow)
# Always use HTTPS-only cookies (we run HTTPS in all environments: local, staging, production)
session_secret_key = config["session_secret_key"]
if not session_secret_key or len(session_secret_key) < 32:
    raise RuntimeError(
        "SESSION_SECRET_KEY must be set to a secure random string (>=32 characters)."
    )

app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret_key,
    max_age=1800,  # 30 minutes
    https_only=True,  # Enforce HTTPS for session cookies
    same_site="lax",  # Allow cookies to be sent on redirects from Auth0
)

# Enable CSRF protection for session-backed browser flows
app.add_middleware(
    CSRFMiddleware,
    secret=session_secret_key,
    sensitive_cookies={"session"},
    cookie_secure=True,
    cookie_samesite="lax",
    header_name="X-CSRFToken",
)

# Configure OAuth with Auth0
# Note: Auth0 callback URLs must be HTTPS only (configured in Auth0 dashboard)
oauth = OAuth()
oauth.register(
    "auth0",
    client_id=config["auth0_client_id"],
    client_secret=config["auth0_client_secret"],
    server_metadata_url=f'https://{config["auth0_domain"]}/.well-known/openid-configuration',
    client_kwargs={"scope": "openid profile email"},
)

# Make oauth available to routers
app.state.oauth = oauth

# Include routers
app.include_router(health)
app.include_router(registration_router)
app.include_router(docs_router)
app.include_router(gpt_router)
app.include_router(oauth_router)
app.include_router(legal_router)
app.include_router(publishing.router)  # Publishing route

# Mount static files for assets (logo, etc.)
app.mount("/static", StaticFiles(directory="."), name="static")

# Set app instance for docs router
set_app_instance(app)

# Mount MCP app at /mcp path
app.mount("/mcp", mcp_app)


if __name__ == "__main__":
    port = config.get("mcp_port")
    logger.info(f"Starting EZ Scheduler on 0.0.0.0:{port}")
    logger.info(f"MCP server will be available at /mcp/")
    logger.info(f"Health check available at /health")

    try:
        uvicorn.run(
            app, host="0.0.0.0", port=port, log_level=config["log_level"].lower()
        )
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        raise
