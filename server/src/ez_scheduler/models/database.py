"""Database configuration and base models"""

import os

from ez_scheduler.config import config
from sqlalchemy import create_engine
from sqlmodel import Session

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


def get_db():
    """Get database session"""
    with Session(engine) as session:
        yield session
