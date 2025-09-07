"""Test-specific configuration loader for EZ Scheduler tests"""

import os

# Test configuration dictionary
test_config = {
    "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
    "mcp_port": 8082,
    "log_level": "INFO",
    "app_base_url": "http://localhost:8082",
}
