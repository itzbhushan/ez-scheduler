"""Database configuration and base models"""

import os

import redis
from sqlalchemy import create_engine
from sqlmodel import Session

from ez_scheduler.config import config

# Database URL from config
DATABASE_URL = config["database_url"]

# Validate DATABASE_URL exists
if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL environment variable is not set. "
        "Make sure to set DATABASE_URL in Railway dashboard or local .env file."
    )

# Create engine
engine = create_engine(DATABASE_URL, echo=os.getenv("DEBUG", "false").lower() == "true")

# Redis URL from config
REDIS_URL = config["redis_url"]

# Create Redis client (singleton) with connection pool configuration
redis_client = redis.from_url(
    REDIS_URL,
    decode_responses=True,
    max_connections=20,  # Max connections in pool
    socket_connect_timeout=5,  # Connection timeout in seconds
    socket_keepalive=True,  # Enable TCP keepalive
    retry_on_timeout=True,  # Retry on timeout
)


def get_db():
    """Get database session"""
    with Session(engine) as session:
        yield session


def get_redis():
    """Get Redis client"""
    return redis_client
