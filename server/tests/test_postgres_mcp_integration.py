"""Tests for PostgreSQL MCP integration with real LLM and real SQL validation"""

import logging

import pytest

from ez_scheduler.auth.models import UserClaims
from ez_scheduler.backends.postgres_mcp_client import (
    PostgresMCPClient,
    generate_sql_query,
)
from tests.config import test_config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@pytest.fixture(scope="function")
async def postgres_mcp_client(llm_client, postgres_container):
    """Pytest fixture to provide a PostgresMCPClient instance with proper cleanup"""
    logger.info("Setting up PostgresMCPClient fixture")

    # Use the test container's connection URL
    database_uri = postgres_container.get_connection_url()
    logger.info(f"Using test database: {database_uri}")

    # Log more details about the container for debugging
    logger.info(f"Container host: {postgres_container.get_container_host_ip()}")
    logger.info(f"Container port: {postgres_container.get_exposed_port(5432)}")
    logger.info(f"Container ID: {postgres_container.get_wrapped_container().id}")

    # Create test config with the container database URI
    container_config = test_config.copy()
    container_config["database_url"] = database_uri

    client = PostgresMCPClient(container_config, llm_client)
    try:
        yield client
    finally:
        # Cleanup handled by PostgresMCPClient.__aexit__
        if hasattr(client, "process") and client.process:
            await client.__aexit__(None, None, None)


class TestMCPServerValidation:
    """Test SQL validation through the postgres-mcp server instead of direct DB connection"""

    async def _validate_sql(
        self, postgres_mcp_client: PostgresMCPClient, sql_query: str, params: dict
    ):
        """Validate SQL using PostgresMCPClient with mcp/postgres server"""
        logger.info(f"📝 Validating SQL via MCP server: {sql_query}")

        try:
            # Create EXPLAIN query to validate syntax without executing data operations
            explain_query = f"EXPLAIN {sql_query}"

            # Interpolate parameters for mcp/postgres
            interpolated_sql = postgres_mcp_client._interpolate_sql_parameters(
                explain_query, params
            )

            # Use the MCP client to send the EXPLAIN query
            result = await postgres_mcp_client._send_mcp_request(
                "tools/call", {"name": "query", "arguments": {"sql": interpolated_sql}}
            )

            print(f"✅ SQL validation passed via MCP server")
            print(f"   Response: {result}")
            return result

        except Exception as e:
            print(f"❌ SQL validation failed via MCP server: {e}")
            raise AssertionError(f"MCP validation failed: {e}")

    @pytest.mark.asyncio
    async def test_mcp_server_validation_basic(self, postgres_mcp_client, llm_client):
        """Test SQL validation through MCP server - basic forms query"""
        # Use Auth0 user ID directly
        test_user_id = "auth0|mcp_test_user_789"

        user_claims = UserClaims(user_id=test_user_id, claims={})

        result = await generate_sql_query(
            llm_client=llm_client,
            request="How many active signup forms do I have",
            user=user_claims,
        )

        # Validate through MCP server
        await self._validate_sql(
            postgres_mcp_client, result.sql_query, result.parameters
        )

        # Verify basic structure
        assert ":user_id" in result.sql_query
        assert result.parameters.get("user_id") == test_user_id
        assert "count" in result.sql_query.lower()
        assert "signup_forms" in result.sql_query.lower()

    # TODO: Add more complex tests when new tables are introduced.
