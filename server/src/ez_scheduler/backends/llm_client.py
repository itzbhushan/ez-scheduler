"""Simplified LLM client for core Anthropic API interactions"""

import httpx
from anthropic import Anthropic


class LLMClient:
    """Client for LLM-based instruction processing"""

    def __init__(self, config: dict):
        # Configure HTTP client with timeouts for CI/CD environments
        http_client = httpx.Client(
            timeout=httpx.Timeout(
                60.0, connect=10.0, read=45.0
            )  # 60s total, 10s connect, 45s read
        )
        self.client = Anthropic(
            api_key=config["anthropic_api_key"], http_client=http_client
        )

    async def process_instruction(
        self, messages: list, max_tokens: int = 1000, system: str = None
    ) -> str:
        """Process messages and return formatted response

        Args:
            messages: List of message dictionaries with 'role' and 'content' keys
            max_tokens: Maximum tokens for the response (default: 1000)
            system: Optional system prompt to guide the LLM's behavior

        Returns:
            Generated text response
        """

        try:
            # Build the request parameters
            request_params = {
                "model": "claude-3-5-sonnet-20241022",
                "max_tokens": max_tokens,
                "messages": messages,
            }

            # Add system prompt if provided
            if system:
                request_params["system"] = system

            response = self.client.messages.create(**request_params)

            return response.content[0].text

        except Exception as e:
            print(
                f"LLM API Error in process_instruction: {e}",
                file=__import__("sys").stderr,
            )
            return "I'm having trouble processing your request. Please try again."
