from fastapi import APIRouter

health = APIRouter()


@health.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "ez-scheduler"}
