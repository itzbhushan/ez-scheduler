#!/usr/bin/env python3
"""EZ Scheduler MCP Server - Signup Form Generation"""

import logging
from datetime import datetime
from typing import Any, Dict

from fastmcp import FastMCP
from dotenv import load_dotenv

from ez_scheduler.tools.create_form import CreateFormTool
from ez_scheduler.llm_client import LLMClient

# Load environment variables
import os
from pathlib import Path

# Try to load .env from project root
project_root = Path(__file__).parent.parent.parent
env_path = project_root / ".env"
load_dotenv(env_path)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Debug: Check if API key is loaded
logger.info(f"API key loaded: {bool(os.getenv('ANTHROPIC_API_KEY'))}")
logger.info(f"Env file path: {env_path}")
logger.info(f"Env file exists: {env_path.exists()}")

# Create MCP app
mcp = FastMCP("ez-scheduler")

# Global instances
create_form_tool = CreateFormTool()
llm_client = LLMClient()

# Storage for conversations and forms
conversations: Dict[str, Dict[str, Any]] = {}
forms: Dict[str, Dict[str, Any]] = {}

@mcp.tool()
async def create_form(user_id: str, initial_request: str) -> str:
    """
    Initiates form creation conversation.
    
    Args:
        user_id: User identifier
        initial_request: Initial form creation request
        
    Returns:
        Response from the form creation process
    """
    logger.info(f"Creating form for user {user_id}: {initial_request}")
    
    # Create or continue conversation
    conversation_id = f"conv_{user_id}_{len(conversations) + 1}"
    
    if conversation_id not in conversations:
        conversations[conversation_id] = {
            "user_id": user_id,
            "status": "active",
            "messages": [],
            "form_data": {}
        }
    
    # Add user message
    conversations[conversation_id]["messages"].append({
        "role": "user",
        "content": initial_request
    })
    
    # Process conversation using LLM
    conversation = conversations[conversation_id]
    
    try:
        # Use LLM to process the instruction
        llm_response = await llm_client.process_form_instruction(
            user_message=initial_request,
            conversation_history=conversation["messages"],
            current_form_data=conversation["form_data"]
        )
        
        # Update form data with extracted information
        extracted_data = llm_response.extracted_data
        if extracted_data.title:
            conversation["form_data"]["title"] = extracted_data.title
        if extracted_data.event_date:
            conversation["form_data"]["event_date"] = extracted_data.event_date
        if extracted_data.location:
            conversation["form_data"]["location"] = extracted_data.location
        if extracted_data.description:
            conversation["form_data"]["description"] = extracted_data.description
        
        # Handle different actions
        if llm_response.action == "create_form" and extracted_data.is_complete:
            # Create the form
            form_data = conversation["form_data"]
            form_id = f"form_{len(forms) + 1}"
            
            forms[form_id] = {
                "id": form_id,
                "user_id": conversation["user_id"],
                "title": form_data.get("title", "Untitled Event"),
                "event_date": form_data.get("event_date", "TBD"),
                "location": form_data.get("location", "TBD"),
                "description": form_data.get("description", ""),
                "is_active": True,
                "created_at": datetime.now().isoformat(),
                "fields": [
                    {"name": "name", "type": "text", "required": True, "label": "Full Name"},
                    {"name": "email", "type": "email", "required": True, "label": "Email Address"},
                    {"name": "phone", "type": "tel", "required": True, "label": "Phone Number"},
                ]
            }
            
            # Generate URL
            form_url = f"http://localhost:8000/forms/{form_id}"
            forms[form_id]["url"] = form_url
            
            conversation["status"] = "completed"
            conversation["form_id"] = form_id
            
            # Use LLM to generate response
            response_text = await llm_client.generate_form_response(forms[form_id])
        else:
            response_text = llm_response.response_text
        
        # Add assistant response
        conversation["messages"].append({
            "role": "assistant",
            "content": response_text
        })
        
        return response_text
        
    except Exception as e:
        logger.error(f"Error processing form creation: {e}")
        error_response = "I'm experiencing technical difficulties. Please try again."
        
        conversation["messages"].append({
            "role": "assistant",
            "content": error_response
        })
        
        return error_response


if __name__ == "__main__":
    port = int(os.getenv("MCP_PORT", "8080"))
    logger.info(f"Starting HTTP MCP server on localhost:{port}")
    mcp.run(transport="streamable-http", host="localhost", port=port)