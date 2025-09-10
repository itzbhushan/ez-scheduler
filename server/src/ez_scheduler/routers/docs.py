"""OpenAPI documentation endpoints"""

from pathlib import Path

from fastapi import APIRouter
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from ez_scheduler.config import config

docs_router = APIRouter(include_in_schema=False)

# Store app reference for use in endpoints
_app_instance = None


def set_app_instance(app):
    """Set the app instance for use in documentation endpoints"""
    global _app_instance
    _app_instance = app


def get_custom_openapi():
    """Generate custom OpenAPI schema"""
    if not _app_instance:
        return {"error": "App instance not set"}

    if _app_instance.openapi_schema:
        return _app_instance.openapi_schema

    openapi_schema = get_openapi(
        title="EZ Scheduler API",
        version="1.0.0",
        description="""
# EZ Scheduler API

A conversational signup form generation and management system.

## Overview

EZ Scheduler provides two main capabilities:

1. **MCP (Model Context Protocol) Interface**: Conversational form creation using AI
2. **Public Web API**: Form serving and registration handling

## Features

### Form Creation (MCP)
- Create signup forms through natural language conversations
- AI-powered form field generation
- Analytics and reporting via natural language queries

### Public Registration API
- Serve HTML registration forms to end users
- Handle form submissions with validation
- Generate confirmation messages

## Authentication

- MCP endpoints require API key authentication
- Public registration endpoints are open access

## Base URLs

- **Staging**: `https://ez-scheduler-staging.up.railway.app`

## Support

For API support, contact support@ez-scheduler.com
        """,
        routes=_app_instance.routes,
        contact={
            "name": "Signup Pro Support",
            "email": "vb@signuppro.ai",
        },
        license_info={
            "name": "MIT",
        },
        servers=[
            {
                "url": config["app_base_url"],
                "description": "API Server",
            },
        ],
    )

    # Add additional metadata with local logo
    openapi_schema["info"]["x-logo"] = {"url": "/static/ez-scheduler-logo.ico"}

    _app_instance.openapi_schema = openapi_schema
    return _app_instance.openapi_schema


@docs_router.get("/v1/api/docs.json")
async def get_openapi_json():
    """Return the OpenAPI JSON schema"""
    return JSONResponse(content=get_custom_openapi())


@docs_router.get("/v1/api/docs")
async def get_swagger_ui():
    """Swagger UI documentation page"""
    return get_swagger_ui_html(
        openapi_url="/v1/api/docs.json",
        title="EZ Scheduler API Documentation",
        swagger_favicon_url="/static/ez-scheduler-logo.ico",
    )


@docs_router.get("/v1/api/redoc")
async def get_redoc():
    """ReDoc documentation page"""
    return get_redoc_html(
        openapi_url="/v1/api/docs.json",
        title="EZ Scheduler API Documentation",
        redoc_favicon_url="/static/ez-scheduler-logo.ico",
    )
