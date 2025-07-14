"""Tests for PostgreSQL MCP integration with real LLM and real SQL validation"""

import logging
from pathlib import Path

import pytest
from dotenv import load_dotenv
from ez_scheduler.services.postgres_mcp_client import (
    PostgresMCPClient,
    generate_sql_query,
)

# Load environment variables from .env file
project_root = Path(__file__).parent.parent.parent
env_path = project_root / ".env"
load_dotenv(env_path)

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

    client = PostgresMCPClient(database_uri, llm_client)
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
        result = await generate_sql_query(
            llm_client=llm_client,
            request="How many active signup forms do I have",
            user_id="test-user",
        )

        # Validate through MCP server
        await self._validate_sql(
            postgres_mcp_client, result.sql_query, result.parameters
        )

        # Verify basic structure
        assert ":user_id" in result.sql_query
        assert result.parameters.get("user_id") == "test-user"
        assert "count" in result.sql_query.lower()
        assert "signup_forms" in result.sql_query.lower()

    @pytest.mark.asyncio
    async def test_mcp_server_validation_complex(self, postgres_mcp_client, llm_client):
        """Test complex analytics query through MCP server"""
        result = await generate_sql_query(
            llm_client=llm_client,
            request="Show my most popular events by registration count",
            user_id="test-user",
        )

        # Validate through MCP server
        await self._validate_sql(
            postgres_mcp_client, result.sql_query, result.parameters
        )

        # Verify structure for analytics query
        assert ":user_id" in result.sql_query
        assert "count" in result.sql_query.lower()
        assert "order by" in result.sql_query.lower()
