"""PostgreSQL client for read-only analytics queries"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import asyncpg
from pydantic import BaseModel, Field

from ez_scheduler.auth.dependencies import User
from ez_scheduler.backends.llm_client import LLMClient
from ez_scheduler.system_prompts import ANALYTICS_FORMATTER_PROMPT, SQL_GENERATOR_PROMPT

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


class PostgresClient:
    """Simple PostgreSQL client for read-only analytics operations"""

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        logger.info("Initialized PostgresClient for analytics queries")

    async def _generate_sql_query(
        self, user: User, analytics_query: str
    ) -> SQLQueryResponse:
        """Generate SQL query using LLM for analytics request"""
        logger.info(f"Generating SQL for analytics query: {analytics_query[:100]}...")

        prompt_context = f"""
            REQUEST: {analytics_query}

            USER_ID: {user.user_id}


            CRITICAL: Always filter results by user_id = :user_id to ensure data isolation.

            Generate a SQL query that fulfills this request. Respond with valid JSON only.
            """
        try:
            response = await self.llm_client.process_instruction(
                messages=[
                    {
                        "role": "user",
                        "content": prompt_context,
                    }
                ],
                max_tokens=500,
                system=SQL_GENERATOR_PROMPT,
            )

            # The system prompt expects JSON response, but we need to handle both formats
            response = response.strip()

            # Parse JSON response
            response_data = json.loads(response)
            return SQLQueryResponse(**response_data)
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            return SQLQueryResponse(
                sql_query="SELECT 1 as error",
                parameters={},
                explanation="Failed to parse SQL generation response",
            )
        except Exception as e:
            logger.error(f"Unexpected error parsing SQL generation response: {e}")
            return SQLQueryResponse(
                sql_query="SELECT 1 as error",
                parameters={},
                explanation="Unexpected error parsing SQL generation response",
            )

    async def _execute_readonly_query(
        self, sql_query: str, parameters: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """Execute read-only SQL query using direct connection"""

        if parameters is None:
            parameters = {}

        logger.info(f"Executing SQL query: {sql_query}")
        logger.info(f"Query parameters: {parameters}")

        # Get the database URL from environment
        readonly_database_url = os.getenv("READ_ONLY_DATABASE_URL")
        if not readonly_database_url:
            raise ValueError(
                "READ_ONLY_DATABASE_URL environment variable is required for analytics operations. "
                "Please set it to a PostgreSQL connection string in the format: "
                "postgresql://username:password@host:port/database"
            )

        # Convert SQLAlchemy-style URL to asyncpg-compatible URL
        if "postgresql+psycopg2://" in readonly_database_url:
            readonly_database_url = readonly_database_url.replace(
                "postgresql+psycopg2://", "postgresql://"
            )

        # Create direct connection for this query
        conn = await asyncpg.connect(readonly_database_url)
        try:
            # Handle parameterized queries
            if parameters:
                # For asyncpg, we need to use $1, $2, etc. format
                # Convert named parameters to positional
                param_values = []
                query_with_positions = sql_query
                for i, (key, value) in enumerate(parameters.items(), 1):
                    query_with_positions = query_with_positions.replace(
                        f":{key}", f"${i}"
                    )
                    param_values.append(value)

                rows = await conn.fetch(query_with_positions, *param_values)
            else:
                rows = await conn.fetch(sql_query)

            # Convert asyncpg records to dictionaries
            results = [dict(row) for row in rows]
            logger.info(f"Query returned {len(results)} rows")
            return results
        finally:
            await conn.close()

    async def process_analytics_query(self, user: User, analytics_query: str) -> str:
        """Process natural language analytics query and return formatted results"""
        # Generate SQL query using LLM
        query_response = await self._generate_sql_query(user, analytics_query)

        # Prepare parameters with actual user ID
        parameters = (
            query_response.parameters.copy() if query_response.parameters else {}
        )
        # Replace placeholder with actual user ID
        if "user_id" in parameters:
            parameters["user_id"] = user.user_id

        # Execute the query with proper parameters
        results = await self._execute_readonly_query(
            query_response.sql_query, parameters
        )

        # Format results for user using the system prompt
        user_content = f"""
        User Query: "{analytics_query}"
        Results: {results}
        """

        summary = await self.llm_client.process_instruction(
            messages=[
                {
                    "role": "user",
                    "content": user_content,
                }
            ],
            max_tokens=1000,
            system=ANALYTICS_FORMATTER_PROMPT,
        )

        return summary
