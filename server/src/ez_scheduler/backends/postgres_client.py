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

    def _validate_user_isolation_in_query(self, query: str) -> None:
        """
        Validate that the query properly enforces user data isolation.

        Security Requirements:
        1. Must include :user_id parameter binding
        2. Must reference signup_forms table (the only table with user_id)
        3. Must filter by signup_forms.user_id = :user_id pattern

        Args:
            query: The SQL query to validate

        Raises:
            ValueError: If the query doesn't meet security requirements
        """
        query_lower = query.lower()

        # Check 1: Must use :user_id parameter binding
        if ":user_id" not in query_lower:
            raise ValueError(
                "Generated SQL query must include :user_id parameter binding"
            )

        # Check 2: Must reference signup_forms table (the only table with user ownership)
        if "signup_forms" not in query_lower:
            raise ValueError(
                "Generated SQL query must reference signup_forms table for user isolation"
            )

        # Check 3: Must have WHERE clause filtering by signup_forms.user_id
        # Look for patterns like: sf.user_id = :user_id or signup_forms.user_id = :user_id
        user_filter_patterns = [
            "sf.user_id = :user_id",
            "sf.user_id=:user_id",
            "signup_forms.user_id = :user_id",
            "signup_forms.user_id=:user_id",
        ]

        has_user_filter = any(
            pattern in query_lower for pattern in user_filter_patterns
        )

        if not has_user_filter:
            raise ValueError(
                "Generated SQL query must filter by signup_forms.user_id = :user_id "
                "(commonly aliased as sf.user_id)"
            )

        logger.debug(
            "✓ Query validation passed: user isolation enforced via signup_forms.user_id"
        )

    async def _execute_readonly_query(
        self, sql_query: str, parameters: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """Execute read-only SQL query using direct connection"""

        if parameters is None:
            parameters = {}

        logger.debug(f"Executing SQL query: {sql_query}")
        logger.debug(f"Query parameters: {parameters}")

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

        # Validate the generated SQL enforces user isolation
        self._validate_user_isolation_in_query(query_response.sql_query)

        # Prepare parameters with actual user ID
        parameters = (
            query_response.parameters.copy() if query_response.parameters else {}
        )

        # the following 2 sets of statements ensure that users only have access to their own data.
        # if the LLM fails to include the user_id parameter (because a user was clever enough
        # to phrase their query to not require it), then reject the query.
        if "user_id" not in parameters:
            raise ValueError(
                "Generated SQL query is missing required user_id parameter."
            )

        # Now that we have confirmed the presence of user_id, force set it to the current user's
        # id so that they do not gain access to others' data (i.e. no exfiltration of other users' data).
        parameters["user_id"] = user.user_id

        # Execute the query with proper parameters. By using a dedicated read-only connection,
        # we ensure that even if the LLM generates a malicious query, it cannot modify data.
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
