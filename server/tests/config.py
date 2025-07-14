"""Test-specific configuration loader for EZ Scheduler tests"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables once for tests
server_dir = Path(__file__).parent.parent
env_path = server_dir / ".env"

if not env_path.exists():
    raise FileNotFoundError(f"Could not find .env file at {env_path}")

load_dotenv(env_path)

# Test configuration dictionary
test_config = {
    "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
    "mcp_port": 8082,  # Different port for tests
    "log_level": "INFO",
}
