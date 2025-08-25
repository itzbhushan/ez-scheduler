"""PostgreSQL MCP Client for read operations using LLM-generated queries"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ez_scheduler.auth.dependencies import UserClaims
from ez_scheduler.backends.llm_client import LLMClient
from ez_scheduler.system_prompts import SQL_GENERATOR_PROMPT

logger = logging.getLogger(__name__)


class SQLQueryResponse(BaseModel):
    """Schema for SQL query generation responses"""

    sql_query: str = Field(..., description="Generated SQL query")
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Query parameters"
    )
    explanation: Optional[str] = Field(
        None, description="Brief explanation of the query"
    )


class PostgresMCPClient:
    """Client for PostgreSQL MCP server operations using stdio transport"""

    def __init__(self, config: dict, llm_client: LLMClient):
        self.database_uri = config["database_url"]
        self.llm_client = llm_client
        self.process = None
        self.request_id = 0
        logger.debug(
            f"Initialized PostgresMCPClient with database URI: {self.database_uri}"
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc_val, _exc_tb):
        """Close the MCP process"""
        if self.process:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()

    async def _ensure_process_running(self):
        """Ensure MCP server process is running"""
        # Start process if needed
        if not self.process or self.process.returncode is not None:
            # Reset state when starting new process
            self.request_id = 0

            logger.info(
                f"Starting mcp-server-postgres with database URI: {self.database_uri}"
            )
            logger.info(f"Original URI was: {self.database_uri}")

            # Start the mcp-server-postgres as a child process using npx
            try:
                self.process = await asyncio.create_subprocess_exec(
                    "npx",
                    "-y",
                    "@modelcontextprotocol/server-postgres",
                    self.database_uri,  # Pass converted database URL
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                logger.debug(
                    f"Started mcp-server-postgres child process (PID: {self.process.pid})"
                )

                # Wait a brief moment to check if process started successfully
                await asyncio.sleep(0.1)
                if self.process.returncode is not None:
                    # Process died immediately, capture stderr
                    stderr_output = await self.process.stderr.read()
                    logger.error(
                        f"MCP postgres server failed to start: {stderr_output.decode()}"
                    )
                    raise RuntimeError(
                        f"MCP postgres server failed to start: {stderr_output.decode()}"
                    )

            except Exception as e:
                logger.error(f"Failed to start mcp-server-postgres: {e}")
                raise RuntimeError(f"Failed to start mcp-server-postgres: {e}")

    async def _send_mcp_request(
        self, method: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send an MCP request via stdio"""
        await self._ensure_process_running()

        self.request_id = 1
        request = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params,
        }

        request_json = json.dumps(request) + "\n"
        logger.debug(f"Sending MCP request: {request_json.strip()}")
        self.process.stdin.write(request_json.encode())
        await self.process.stdin.drain()

        # Read response
        response_line = await self.process.stdout.readline()
        logger.debug(f"Raw MCP response: {response_line}")

        response = json.loads(response_line.decode())
        logger.debug(f"Parsed MCP response: {response}")

        if "error" in response:
            raise Exception(f"MCP Error: {response['error']}")

        return response.get("result", {})

    def _interpolate_sql_parameters(self, sql: str, parameters: Dict[str, Any]) -> str:
        """Safely interpolate parameters into SQL query for mcp/postgres"""
        # Simple parameter interpolation - replace :param_name with quoted values
        for param_name, param_value in parameters.items():
            placeholder = f":{param_name}"
            if isinstance(param_value, str):
                # Escape single quotes in string values
                escaped_value = param_value.replace("'", "''")
                safe_value = f"'{escaped_value}'"
            elif isinstance(param_value, bool):
                safe_value = str(param_value).lower()
            elif param_value is None:
                safe_value = "NULL"
            else:
                safe_value = str(param_value)

            sql = sql.replace(placeholder, safe_value)

        return sql

    async def query_from_intent(
        self,
        user_intent: str,
        user: UserClaims,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Execute a query by having LLM generate SQL from user's natural language intent"""
        try:
            # Use LLM to generate SQL query from user intent
            sql_response = await generate_sql_query(
                llm_client=self.llm_client,
                request=user_intent,
                user=user,
                context=context or {},
            )

            # Interpolate parameters into SQL for mcp/postgres
            interpolated_sql = self._interpolate_sql_parameters(
                sql_response.sql_query, sql_response.parameters
            )

            # Execute the generated SQL via MCP stdio
            result = await self._send_mcp_request(
                "tools/call", {"name": "query", "arguments": {"sql": interpolated_sql}}
            )

            return result.get("content", [])

        except Exception as e:
            logger.error(f"Error executing LLM-generated query via MCP: {e}")
            raise


async def generate_sql_query(
    llm_client: LLMClient,
    request: str,
    user: UserClaims,
    context: Dict[str, Any] = None,
) -> SQLQueryResponse:
    """Generate SQL query from natural language request"""

    # Ensure user_id is always included in context
    context = context or {}
    context["user_id"] = user.user_id

    prompt_context = f"""
REQUEST: {request}

USER_ID: {user.user_id}

CONTEXT: {json.dumps(context, indent=2)}

CRITICAL: Always filter results by user_id = :user_id to ensure data isolation.

Generate a SQL query that fulfills this request. Respond with valid JSON only."""

    try:
        response_text = await llm_client.process_instruction(
            messages=[{"role": "user", "content": prompt_context}],
            max_tokens=500,
            system=SQL_GENERATOR_PROMPT,
        )

        # Parse JSON response
        try:
            response_data = json.loads(response_text)
            return SQLQueryResponse(**response_data)
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            return SQLQueryResponse(
                sql_query="SELECT 1 as error",
                parameters={},
                explanation="Failed to parse SQL generation response",
            )

    except Exception as e:
        logger.error(f"LLM API Error in SQL generation: {e}")
        return SQLQueryResponse(
            sql_query="SELECT 1 as error",
            parameters={},
            explanation=f"Error generating SQL: {str(e)}",
        )
