"""Test for LLM client connectivity and functionality"""

import pytest


@pytest.mark.asyncio
async def test_llm_client_connectivity(llm_client):
    """Test that LLM client can connect and respond"""
    # Verify client is available
    assert llm_client is not None, "LLM client should be available"
    assert (
        llm_client.client is not None
    ), "LLM client should have an active client connection"

    # Test basic API connectivity
    response = await llm_client.process_instruction(
        messages=[{"role": "user", "content": "Hello, respond with just 'Hello'"}],
        max_tokens=10,
    )

    assert response is not None, "Should receive a response from LLM"
    assert isinstance(response, str), "Response should be a string"
    assert len(response) > 0, "Response should not be empty"
