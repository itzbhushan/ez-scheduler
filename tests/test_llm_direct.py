#!/usr/bin/env python3
"""Test script to verify LLM client fix"""

import asyncio
import sys
from pathlib import Path

# Add src to path so we can import ez_scheduler modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from ez_scheduler.llm_client import LLMClient

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
            
        # Test the process_form_instruction method
        result = await client.process_form_instruction(
            user_message="Create a signup form for my birthday party on March 15th at Central Park",
            conversation_history=[],
            current_form_data={}
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