"""Shared test configuration and fixtures for EZ Scheduler tests"""

import asyncio
import os
import subprocess
import time
from pathlib import Path

import pytest
from dotenv import load_dotenv
from ez_scheduler.llm_client import LLMClient
from fastmcp.client import Client, StreamableHttpTransport

# Load environment variables from .env file
project_root = Path(__file__).parent.parent
env_path = project_root / ".env"
load_dotenv(env_path)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def verify_test_requirements():
    """Verify required environment variables and dependencies for tests"""
    # Check for Anthropic API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.exit("ANTHROPIC_API_KEY environment variable is required for tests")

    # Check for PostgreSQL MCP URL
    if not os.getenv("POSTGRES_MCP_URL"):
        pytest.exit("POSTGRES_MCP_URL environment variable is required for tests")

    return True


@pytest.fixture(scope="session")
async def mcp_server_process():
    """Start the HTTP MCP server once for the entire test session"""
    # Set environment variables - get current directory for relative paths
    env = os.environ.copy()
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env["PYTHONPATH"] = os.path.join(current_dir, "src")
    env["MCP_PORT"] = "8082"  # Use different port for tests

    # Start the HTTP server process
    process = subprocess.Popen(
        [
            os.path.join(current_dir, ".venv", "bin", "python"),
            "src/ez_scheduler/main.py",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=current_dir,
    )

    # Wait for HTTP server to be ready
    await _wait_for_server("http://localhost:8082")

    yield process

    # Clean up: terminate the process
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


async def _wait_for_server(url: str, timeout: int = 30):
    """Wait for the HTTP server to be ready"""
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            # Try to connect to the MCP server using StreamableHttpTransport
            transport = StreamableHttpTransport(f"{url}/mcp")
            async with Client(transport) as client:
                # Try to list tools as a simple connectivity test
                await client.list_tools()
                return
        except Exception:
            pass
        await asyncio.sleep(0.5)

    raise TimeoutError(f"Server at {url} did not become ready within {timeout} seconds")


@pytest.fixture(scope="session")
def llm_client():
    """Create a shared LLMClient instance for all tests"""
    return LLMClient()


@pytest.fixture
def mcp_client():
    """Create an MCP client connected to the test server"""
    return StreamableHttpTransport("http://localhost:8082/mcp")
