#!/usr/bin/env python3
"""EZ Scheduler - Combined MCP and Web Server"""

import logging

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastmcp import FastMCP

from ez_scheduler.config import config
from ez_scheduler.routers.docs import docs_router, set_app_instance
from ez_scheduler.routers.gpt_actions import router as gpt_router
from ez_scheduler.routers.health import health
from ez_scheduler.routers.legal import router as legal_router
from ez_scheduler.routers.mcp_server import mcp_app
from ez_scheduler.routers.oauth import router as oauth_router
from ez_scheduler.routers.registration import router as registration_router

# Configure logging
logging.basicConfig(level=getattr(logging, config["log_level"]))
logger = logging.getLogger(__name__)


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

app.include_router(health)
app.include_router(registration_router)
app.include_router(docs_router)
app.include_router(gpt_router)
app.include_router(oauth_router)
app.include_router(legal_router)

# Mount static files for assets (logo, etc.)
app.mount("/static", StaticFiles(directory="."), name="static")

# Set app instance for docs router
set_app_instance(app)

# Mount this at the end...
app.mount("/", mcp_app)


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
