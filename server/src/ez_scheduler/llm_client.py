"""Simplified LLM client for core Anthropic API interactions"""

import os
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv


class LLMClient:
    """Client for LLM-based instruction processing"""

    def __init__(self):
        # Load environment variables from project root
        project_root = Path(__file__).parent.parent.parent
        env_path = project_root / ".env"
        load_dotenv(env_path)

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                f"ANTHROPIC_API_KEY not found. Please set the API key in {env_path}"
            )

        self.client = Anthropic(api_key=api_key)

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
