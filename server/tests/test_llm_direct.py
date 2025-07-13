#!/usr/bin/env python3
"""Test script to verify LLM client fix"""

import asyncio

from ez_scheduler.llm_client import LLMClient
from ez_scheduler.tools.create_form import process_form_instruction


async def test_llm_client():
    """Test the LLMClient with API key fix"""
    print("🧪 Testing LLMClient with API key fix")
    print("=" * 50)

    try:
        client = LLMClient()
        print(f"✅ LLMClient created. Client available: {client.client is not None}")

        if client.client is None:
            print("❌ No client available - API key issue")
            return False

        # Test the process_instruction method
        response = await client.process_instruction(
            messages=[{"role": "user", "content": "Hello, can you help me?"}],
            max_tokens=100,
        )

        print("✅ process_instruction executed successfully!")
        print(f"📝 Response: {response}")

        # Test the form creation functionality
        result = await process_form_instruction(
            llm_client=client,
            user_message="Create a signup form for my birthday party on March 15th at Central Park",
            conversation_history=[],
            current_form_data={},
        )

        print("✅ process_form_instruction executed successfully!")
        print(f"📝 Response: {result.response_text}")
        print(f"📊 Action: {result.action}")
        print(f"🎯 Is complete: {result.extracted_data.is_complete}")

        if result.extracted_data.is_complete:
            print("✅ Form data extracted successfully!")
            print(f"   - Title: {result.extracted_data.title}")
            print(f"   - Date: {result.extracted_data.event_date}")
            print(f"   - Location: {result.extracted_data.location}")

        return True

    except Exception as e:
        print(f"❌ LLMClient test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_llm_client())
    if success:
        print("\n🎉 LLM client fix verified! The API is working correctly.")
    else:
        print("\n⚠️  LLM client fix needs more work.")
