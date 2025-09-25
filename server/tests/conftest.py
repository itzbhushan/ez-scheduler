"""Shared test configuration and fixtures for EZ Scheduler tests"""

import asyncio
import logging
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fastmcp.client import Client, StreamableHttpTransport
from sqlmodel import Session, create_engine
from testcontainers.postgres import PostgresContainer

from ez_scheduler.auth.dependencies import get_current_user
from ez_scheduler.auth.models import User
from ez_scheduler.backends.llm_client import LLMClient
from ez_scheduler.main import app
from ez_scheduler.models.database import get_db
from ez_scheduler.services.form_field_service import FormFieldService
from ez_scheduler.services.registration_service import RegistrationService
from ez_scheduler.services.signup_form_service import SignupFormService
from ez_scheduler.services.timeslot_service import TimeslotService
from tests.config import test_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.fixture(scope="session", autouse=True)
def verify_test_requirements():
    """Verify required environment variables and dependencies for tests"""
    # Check for Anthropic API key
    if not test_config["anthropic_api_key"]:
        pytest.exit("ANTHROPIC_API_KEY environment variable is required for tests")

    return True


@pytest.fixture(scope="session", autouse=True)
async def mcp_server_process(postgres_container):
    """Start the HTTP MCP server once for the entire test session"""
    env = os.environ.copy()
    env["MCP_PORT"] = str(test_config["mcp_port"])  # Use test config port
    # Ensure the app_base_url used in responses matches the test server
    env["APP_BASE_URL"] = test_config["app_base_url"]

    # Ensure the MCP server uses the same database as the test
    database_url = postgres_container.get_connection_url()
    env["DATABASE_URL"] = database_url

    # Start the HTTP server process
    process = subprocess.Popen(
        [sys.executable, "src/ez_scheduler/main.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    # Wait for HTTP server to be ready
    await _wait_for_server(test_config["app_base_url"])

    yield process

    process.terminate()


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
def postgres_container():
    """Create a PostgreSQL test container for the test session"""
    with PostgresContainer("postgres:16") as postgres:
        # Set up database URI in environment
        database_url = postgres.get_connection_url()
        os.environ["DATABASE_URL"] = database_url
        os.environ["READ_ONLY_DATABASE_URL"] = database_url  # Use same DB for tests
        os.environ["sqlalchemy.url"] = database_url

        # Run Alembic migrations to set up schema
        _run_migrations(database_url)

        yield postgres


def _run_migrations(database_url: str):
    """Run Alembic migrations on the test database"""

    # Get the server directory (where alembic.ini is located)
    server_dir = Path(__file__).parent.parent
    alembic_ini = server_dir / "alembic.ini"

    # Set environment variable for database URL
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url

    try:
        # Run alembic upgrade head
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(alembic_ini), "upgrade", "head"],
            cwd=server_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            logger.error(f"Alembic migration failed: {result.stderr}")
            raise RuntimeError(f"Failed to run migrations: {result.stderr}")
        else:
            logger.info("Database schema setup completed successfully")

    except Exception as e:
        logger.error(f"Error running migrations: {e}")
        raise


@pytest.fixture(scope="session")
def llm_client():
    """Create a shared LLMClient instance for all tests"""
    return LLMClient(test_config)


@pytest.fixture
def mcp_client(mcp_server_process):
    """Create an MCP client connected to the test server"""
    # mcp_server_process dependency ensures server is running
    _ = mcp_server_process  # Dependency ensures server startup
    return StreamableHttpTransport(f"{test_config['app_base_url']}/mcp/")


@pytest.fixture
def _db_session(postgres_container):
    """Private DB session for fixtures only.

    Do not use this fixture directly in tests. Prefer higher-level service
    fixtures like `signup_service`, `registration_service`, or
    `form_field_service` to avoid coupling tests to the session internals.
    """

    # Get the database URL from the PostgreSQL container
    database_url = postgres_container.get_connection_url()

    # Create engine and session
    engine = create_engine(database_url)
    session = Session(engine)

    yield session

    # Cleanup
    session.close()


@pytest.fixture
def registration_service(_db_session, llm_client):
    """Create a RegistrationService instance for testing"""
    return RegistrationService(_db_session, llm_client)


@pytest.fixture
def signup_service(_db_session):
    """Create a SignupFormService instance for testing"""
    return SignupFormService(_db_session)


@pytest.fixture
def form_field_service(_db_session):
    """Create a FormFieldService instance for testing"""

    return FormFieldService(_db_session)


@pytest.fixture
def timeslot_service(_db_session):
    """Create a TimeslotService instance for testing.

    Tests should prefer using service fixtures over raw DB sessions.
    """
    return TimeslotService(_db_session)


@pytest.fixture
def mock_current_user():
    """Create a mock current user for testing authenticated endpoints"""

    def _create_mock_user():
        """Create a User object for testing"""
        user_id = str(uuid.uuid4())
        claims = {
            "iss": "https://ez-scheduler-dev.us.auth0.com/",
            "aud": "test-audience",
            "scope": "openid profile email",
            "permissions": [],
        }
        return User(user_id=user_id, claims=claims)

    return _create_mock_user


@pytest.fixture
def authenticated_client(mock_current_user, _db_session):
    """Create a test client that bypasses authentication and uses test database"""

    # Store original overrides to restore them later
    original_overrides = app.dependency_overrides.copy()

    # Create a test user
    test_user = mock_current_user()

    # Override the get_current_user dependency
    async def mock_get_current_user():
        return test_user

    # Override the database dependency to use test database
    def get_test_db():
        return _db_session

    # Clear all existing overrides and set only our test overrides
    app.dependency_overrides.clear()
    app.dependency_overrides[get_current_user] = mock_get_current_user
    app.dependency_overrides[get_db] = get_test_db

    client = TestClient(app)

    yield client, test_user

    # Completely restore original state
    app.dependency_overrides.clear()
    app.dependency_overrides.update(original_overrides)
