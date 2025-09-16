"""Configuration loader for EZ Scheduler with environment-specific support"""

import os
from pathlib import Path

from dotenv import load_dotenv

server_dir = Path(__file__).parent.parent.parent
env_path = server_dir / ".env"

# Load .env file if it exists. For local development only.
if env_path.exists():
    load_dotenv(env_path)

# Configuration dictionary - set once at initialization
config = {
    "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
    "database_url": os.getenv("DATABASE_URL"),
    "readonly_database_url": os.getenv("READ_ONLY_DATABASE_URL"),
    "mcp_port": int(os.getenv("MCP_PORT")),
    "log_level": os.getenv("LOG_LEVEL", "INFO"),
    "app_base_url": os.getenv("APP_BASE_URL"),
    "auth0_domain": os.getenv("AUTH0_DOMAIN"),
    "auth0_management_client_id": os.getenv("AUTH0_MANAGEMENT_CLIENT_ID"),
    "auth0_management_client_secret": os.getenv("AUTH0_MANAGEMENT_CLIENT_SECRET"),
    "mailgun_api_key": os.getenv("MAILGUN_API_KEY"),
    "mailgun_domain": os.getenv("MAILGUN_DOMAIN"),
    "sender_email": os.getenv("SENDER_EMAIL"),
    # Optional UI theme selection for public forms. Example: "golu"
    "default_form_theme": os.getenv("DEFAULT_FORM_THEME"),
    "environment": os.getenv("ENVIRONMENT"),
}
