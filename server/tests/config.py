"""Test-specific configuration loader for EZ Scheduler tests"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables once for tests (optional .env file)
server_dir = Path(__file__).parent.parent
env_path = server_dir / ".env"

# Only load .env file if it exists (for local development)
# CI/CD provides environment variables directly
if env_path.exists():
    load_dotenv(env_path)

# Test configuration dictionary
test_config = {
    "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
    "mcp_port": 8082,  # Different port for tests (don't use env var here)
    "log_level": os.getenv("LOG_LEVEL", "INFO"),
    "database_url": os.getenv(
        "DATABASE_URL", "postgresql://ez_user:ez_password@localhost:5432/ez_scheduler"
    ),
    "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379"),
}
