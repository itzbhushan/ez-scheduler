"""Simplified LLM client for core Anthropic API interactions"""

import re

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
        self.model = config.get("anthropic_model")

    @staticmethod
    def _clean_json_response(response: str) -> str:
        """
        Clean JSON response by removing markdown code block formatting.

        Handles responses wrapped in:
        - ```json ... ```
        - ``` ... ```
        - Leading/trailing whitespace

        Args:
            response: Raw LLM response text

        Returns:
            Cleaned response with markdown formatting removed
        """
        # Remove leading/trailing whitespace
        cleaned = response.strip()

        # Remove markdown code blocks with optional language tag
        # Pattern: ```json\n{...}\n``` or ```\n{...}\n```
        if cleaned.startswith("```"):
            # Remove opening fence (with optional language tag)
            cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
            # Remove closing fence
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)
            # Clean up any remaining whitespace
            cleaned = cleaned.strip()

        return cleaned

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

        # Build the request parameters
        request_params = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }

        # Add system prompt if provided
        if system:
            request_params["system"] = system

        response = self.client.messages.create(**request_params)

        # Clean JSON response to remove markdown formatting
        raw_text = response.content[0].text
        return self._clean_json_response(raw_text)
