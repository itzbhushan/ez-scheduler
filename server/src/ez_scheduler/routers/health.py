import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, text

from ez_scheduler.models.database import engine

health = APIRouter()


@health.get("/health")
async def health_check():
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "service": "ez-scheduler",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": os.getenv("ENVIRONMENT", "development"),
    }


@health.get("/health/detailed")
async def detailed_health_check():
    """Detailed health check with database and dependency checks"""
    health_status = {
        "status": "healthy",
        "service": "ez-scheduler",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": os.getenv("ENVIRONMENT", "development"),
        "checks": {},
    }

    # Database connectivity check
    try:
        with Session(engine) as session:
            result = session.exec(text("SELECT 1")).first()
            health_status["checks"]["database"] = "healthy" if result else "unhealthy"
    except Exception as e:
        health_status["checks"]["database"] = f"unhealthy: {str(e)}"
        health_status["status"] = "unhealthy"

    # Environment variables check
    required_env_vars = ["DATABASE_URL"]
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        health_status["checks"]["environment"] = f"missing: {', '.join(missing_vars)}"
        health_status["status"] = "unhealthy"
    else:
        health_status["checks"]["environment"] = "healthy"

    if health_status["status"] == "unhealthy":
        raise HTTPException(status_code=503, detail=health_status)

    return health_status
