"""Test for LLM client connectivity and functionality"""

import pytest

from ez_scheduler.tools.create_form import process_form_instruction


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


@pytest.mark.asyncio
async def test_llm_client_form_processing(llm_client):
    """Test that LLM client can process form instructions"""
    result = await process_form_instruction(
        llm_client=llm_client,
        user_message="Create a signup form for my birthday party on March 15th, 2024 at Central Park",
        conversation_history=[],
        current_form_data={},
    )

    # Verify response structure
    assert result is not None, "Should receive a result"
    assert hasattr(result, "response_text"), "Should have response_text"
    assert hasattr(result, "action"), "Should have action"
    assert hasattr(result, "extracted_data"), "Should have extracted_data"

    # Verify response content
    assert result.response_text is not None, "Should have response text"
    assert result.action in [
        "continue",
        "create_form",
        "clarify",
    ], "Should have valid action"
    assert result.extracted_data is not None, "Should have extracted data"

    # Test form data extraction
    if result.extracted_data.is_complete:
        assert result.extracted_data.title is not None, "Should extract title"
        assert result.extracted_data.event_date is not None, "Should extract event date"
        assert result.extracted_data.location is not None, "Should extract location"
        assert (
            "2024-03-15" in result.extracted_data.event_date
        ), "Should parse date correctly"
        assert (
            "central park" in result.extracted_data.location.lower()
        ), "Should extract location"
