"""Create Form Tool - Handles form creation conversations using LLM"""

from typing import Any, Dict
from datetime import datetime

from mcp.types import CallToolResult, TextContent
from ..llm_client import LLMClient


class CreateFormTool:
    """Tool for creating signup forms through LLM-powered conversation"""
    
    def __init__(self):
        self.conversations: Dict[str, Dict[str, Any]] = {}
        self.forms: Dict[str, Dict[str, Any]] = {}
        self.llm_client = LLMClient()
    
    async def handle(self, args: Dict[str, Any]) -> CallToolResult:
        """Handle form creation request"""
        user_id = args["user_id"]
        initial_request = args["initial_request"]
        
        # Create or continue conversation
        conversation_id = f"conv_{user_id}_{len(self.conversations) + 1}"
        
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = {
                "user_id": user_id,
                "status": "active",
                "messages": [],
                "form_data": {}
            }
        
        # Add user message
        self.conversations[conversation_id]["messages"].append({
            "role": "user",
            "content": initial_request
        })
        
        # Process conversation using LLM
        response = await self._process_conversation(conversation_id, initial_request)
        
        # Add assistant response
        self.conversations[conversation_id]["messages"].append({
            "role": "assistant",
            "content": response
        })
        
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=response
                )
            ]
        )
    
    async def _process_conversation(self, conversation_id: str, message: str) -> str:
        """Process conversation using LLM to understand user intent"""
        conversation = self.conversations[conversation_id]
        
        # Use LLM to process the instruction
        llm_response = await self.llm_client.process_form_instruction(
            user_message=message,
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
            return await self._create_form_from_conversation(conversation_id)
        elif llm_response.action == "continue":
            return llm_response.response_text
        elif llm_response.action == "clarify":
            return llm_response.response_text
        else:
            return llm_response.response_text
    
    async def _create_form_from_conversation(self, conversation_id: str) -> str:
        """Create form from conversation data"""
        conversation = self.conversations[conversation_id]
        form_data = conversation["form_data"]
        
        # Generate form
        form_id = f"form_{len(self.forms) + 1}"
        self.forms[form_id] = {
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
        self.forms[form_id]["url"] = form_url
        
        conversation["status"] = "completed"
        conversation["form_id"] = form_id
        
        # Use LLM to generate a professional response
        return await self.llm_client.generate_form_response(self.forms[form_id])