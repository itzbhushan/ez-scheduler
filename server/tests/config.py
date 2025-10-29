"""Test-specific configuration loader for EZ Scheduler tests"""

import os

# Test configuration dictionary
test_config = {
    "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
    "anthropic_model": os.getenv("ANTHROPIC_MODEL"),
    "mcp_port": 8082,
    "log_level": "INFO",
    "app_base_url": "http://localhost:8082",
    "mailgun_api_key": os.getenv("MAILGUN_API_KEY"),
    "mailgun_domain": os.getenv("MAILGUN_DOMAIN"),
    "sender_email": os.getenv("SENDER_EMAIL"),
}
