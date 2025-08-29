"""Configuration loader for EZ Scheduler with environment-specific support"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Determine environment and load appropriate .env file
environment = os.getenv("ENVIRONMENT", "local")
server_dir = Path(__file__).parent.parent.parent

# Load environment-specific .env file only for local and test environments
# Staging and production use Railway environment variables directly
if environment in ["local", "test"]:
    env_files = {"local": ".env", "test": ".env.test"}

    env_file = env_files.get(environment, ".env")
    env_path = server_dir / env_file

    # Load .env file if it exists
    if env_path.exists():
        load_dotenv(env_path)


# Configuration dictionary - set once at initialization
config = {
    "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
    "database_url": os.getenv("DATABASE_URL"),
    "readonly_database_url": os.getenv("READ_ONLY_DATABASE_URL"),
    "mcp_port": int(os.getenv("MCP_PORT", "8080")),
    "log_level": os.getenv("LOG_LEVEL", "INFO"),
    "app_base_domain": os.getenv("APP_BASE_DOMAIN"),
    "app_base_url": os.getenv("APP_BASE_URL"),
    "admin_api_key": os.getenv("ADMIN_API_KEY"),
    "auth0_client_secret": os.getenv("AUTH0_CLIENT_SECRET"),
    "redirect_uri": os.getenv("REDIRECT_URI"),
    "auth0_domain": os.getenv("AUTH0_DOMAIN"),
    "auth0_client_id": os.getenv("AUTH0_CLIENT_ID"),
}
