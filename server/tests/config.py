"""Test-specific configuration loader for EZ Scheduler tests"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables once for tests (optional .env file)
server_dir = Path(__file__).parent.parent
env_path = server_dir / ".env.test"

# Only load .env file if it exists (for local development)
# CI/CD provides environment variables directly
if env_path.exists():
    load_dotenv(env_path)

# Set default environment variables for tests if not already set
if not os.getenv("READ_ONLY_DATABASE_URL"):
    os.environ["READ_ONLY_DATABASE_URL"] = (
        "postgresql://ez_analytics_readonly:test_password@localhost:5432/ez_scheduler"
    )

if not os.getenv("ANALYTICS_DB_PASSWORD"):
    os.environ["ANALYTICS_DB_PASSWORD"] = "test_password"

# Test configuration dictionary
test_config = {
    "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
    "mcp_port": int(
        os.getenv("MCP_PORT", "8082")
    ),  # Use CI/CD env var or default 8082 for tests
    "log_level": os.getenv("LOG_LEVEL", "INFO"),
    "database_url": os.getenv(
        "DATABASE_URL", "postgresql://ez_user:ez_password@localhost:5432/ez_scheduler"
    ),
    "redis_url": os.getenv("REDIS_URL", "redis://localhost:6379"),
    "read_only_database_url": os.getenv(
        "READ_ONLY_DATABASE_URL",
        "postgresql://ez_analytics_readonly:test_password@localhost:5432/ez_scheduler",
    ),
    "app_base_domain": os.getenv("APP_BASE_DOMAIN", "http://localhost"),
    "app_base_url": os.getenv("APP_BASE_URL"),
    "admin_api_key": os.getenv("ADMIN_API_KEY"),
}
