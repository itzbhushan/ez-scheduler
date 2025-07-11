"""Create Form Tool - Handles form creation conversations using LLM"""

import logging
import uuid
from typing import Any, Dict
from datetime import datetime

from ..llm_client import LLMClient

logger = logging.getLogger(__name__)

# Global storage - shared across the application
conversations: Dict[str, Dict[str, Any]] = {}
forms: Dict[str, Dict[str, Any]] = {}
llm_client = LLMClient()




async def create_form_handler(user_id: str, initial_request: str) -> str:
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
            title = form_data.get("title", "Untitled Event")
            event_date = form_data.get("event_date", "TBD")
            
            # Generate meaningful form ID using LLM
            base_form_id = await llm_client.generate_form_id(title, event_date)
            
            # Add UUID to ensure uniqueness
            unique_id = str(uuid.uuid4())[:8]  # First 8 chars of UUID
            form_id = f"{base_form_id}-{unique_id}"
            
            forms[form_id] = {
                "id": form_id,
                "user_id": conversation["user_id"],
                "title": title,
                "event_date": event_date,
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
            
            conversation["status"] = "completed"
            conversation["form_id"] = form_id
            
            # Use LLM to generate response with dynamic URL
            form_data_with_url = forms[form_id].copy()
            form_data_with_url["url"] = f"http://localhost:8000/forms/{form_id}"
            response_text = await llm_client.generate_form_response(form_data_with_url)
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
