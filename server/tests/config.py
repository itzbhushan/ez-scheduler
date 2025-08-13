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
    "app_base_domain": os.getenv("APP_BASE_DOMAIN", "http://localhost"),
}

# Construct full base URL from domain and port for tests
test_config["app_base_url"] = (
    f"{test_config['app_base_domain']}:{test_config['mcp_port']}"
)
