"""Simple configuration loader for EZ Scheduler"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables once
server_dir = Path(__file__).parent.parent.parent
env_path = server_dir / ".env"

if not env_path.exists():
    raise FileNotFoundError(f"Could not find .env file at {env_path}")

load_dotenv(env_path)

# Configuration dictionary
config = {
    "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
    "database_url": os.getenv("DATABASE_URL"),
    "mcp_port": int(os.getenv("MCP_PORT", "8080")),
    "log_level": os.getenv("LOG_LEVEL", "INFO"),
}
