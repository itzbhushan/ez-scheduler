#!/usr/bin/env python3
"""EZ Scheduler - Combined MCP and Web Server"""

import logging
import uuid

import uvicorn
from ez_scheduler.config import config
from ez_scheduler.routers.health import health
from ez_scheduler.routers.mcp_server import mcp_app
from ez_scheduler.routers.registration import router as registration_router
from fastapi import FastAPI
from fastmcp import FastMCP

# Configure logging
logging.basicConfig(level=getattr(logging, config["log_level"]))
logger = logging.getLogger(__name__)


# Create FastAPI app
app = FastAPI(
    title="EZ Scheduler",
    description="Signup Form Generation and Management",
    lifespan=mcp_app.lifespan,
)

app.include_router(health)
app.include_router(registration_router)
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
