"""LLM client for processing user instructions"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from anthropic import Anthropic
from pydantic import BaseModel, Field
from dotenv import load_dotenv


class FormExtractionSchema(BaseModel):
    """Schema for form extraction from user instructions"""
    title: Optional[str] = Field(None, description="Event title or name")
    event_date: Optional[str] = Field(None, description="Event date")
    location: Optional[str] = Field(None, description="Event location")
    description: Optional[str] = Field(None, description="Event description")
    additional_fields: Optional[list] = Field(default_factory=list, description="Additional form fields requested")
    is_complete: bool = Field(False, description="Whether all required info is present")
    next_question: Optional[str] = Field(None, description="Next question to ask user if not complete")


class ConversationResponse(BaseModel):
    """Schema for conversation responses"""
    response_text: str = Field(..., description="Response to send to user")
    extracted_data: FormExtractionSchema = Field(..., description="Extracted form data")
    action: str = Field(..., description="Action to take: 'continue', 'create_form', 'clarify'")


class LLMClient:
    """Client for LLM-based instruction processing"""
    
    def __init__(self):
        # Load environment variables from project root
        project_root = Path(__file__).parent.parent.parent
        env_path = project_root / ".env"
        load_dotenv(env_path)
        
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            print("Warning: ANTHROPIC_API_KEY not found. LLM features will be disabled.", file=__import__('sys').stderr)
            print(f"Tried loading from: {env_path}", file=__import__('sys').stderr)
            self.client = None
        else:
            self.client = Anthropic(api_key=api_key)
    
    async def process_form_instruction(
        self, 
        user_message: str, 
        conversation_history: list = None,
        current_form_data: Dict[str, Any] = None
    ) -> ConversationResponse:
        """Process user instruction for form creation/modification"""
        
        conversation_history = conversation_history or []
        current_form_data = current_form_data or {}
        
        system_prompt = """You are an expert form builder assistant. Your job is to help users create signup forms by extracting information from their natural language instructions.

REQUIRED FORM FIELDS:
- title: Event name/title
- event_date: When the event occurs
- location: Where the event is held

STANDARD FORM FIELDS (always included):
- name: Full name (required)
- email: Email address (required)  
- phone: Phone number (required)

INSTRUCTIONS:
1. Extract form information from the user's message
2. Identify what information is missing
3. Generate appropriate follow-up questions
4. Determine if enough info exists to create the form
5. Return structured JSON response

RESPONSE FORMAT:
{
    "response_text": "Your response to the user",
    "extracted_data": {
        "title": "extracted title or null",
        "event_date": "extracted date or null",
        "location": "extracted location or null", 
        "description": "extracted description or null",
        "additional_fields": ["any additional fields requested"],
        "is_complete": false,
        "next_question": "Next question to ask if not complete"
    },
    "action": "continue|create_form|clarify"
}

EXAMPLES:
User: "Create a form for my birthday party on Jan 15th at Central Park"
Response: Extract title="Birthday Party", event_date="Jan 15th", location="Central Park", is_complete=true, action="create_form"

User: "I need a signup form for my event"
Response: is_complete=false, next_question="What is your event called?", action="continue"
"""

        # Build conversation context
        context = f"""
CURRENT FORM DATA: {json.dumps(current_form_data, indent=2)}

CONVERSATION HISTORY:
{json.dumps(conversation_history[-5:], indent=2) if conversation_history else "No previous messages"}

USER MESSAGE: {user_message}
"""

        # Check if client is available
        if not self.client:
            return ConversationResponse(
                response_text="LLM service is currently unavailable. Please ensure your API key is configured.",
                extracted_data=FormExtractionSchema(),
                action="clarify"
            )

        try:
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                system=system_prompt,
                messages=[{"role": "user", "content": context}]
            )
            
            response_text = response.content[0].text
            
            # Parse JSON response
            try:
                response_data = json.loads(response_text)
                return ConversationResponse(**response_data)
            except json.JSONDecodeError:
                # Fallback if JSON parsing fails
                return ConversationResponse(
                    response_text="I'm having trouble processing your request. Could you please rephrase it?",
                    extracted_data=FormExtractionSchema(),
                    action="clarify"
                )
                
        except Exception as e:
            # Error handling with logging
            print(f"LLM API Error: {e}", file=__import__('sys').stderr)
            return ConversationResponse(
                response_text="I'm experiencing technical difficulties. Please try again.",
                extracted_data=FormExtractionSchema(),
                action="clarify"
            )
    
    async def generate_form_response(self, form_data: Dict[str, Any]) -> str:
        """Generate a form creation confirmation response"""
        
        system_prompt = """Generate a friendly, professional response confirming that a signup form has been created. Include the form details and next steps.

Make the response engaging and helpful. Format it nicely with clear sections."""

        context = f"""
FORM CREATED:
{json.dumps(form_data, indent=2)}

Generate a confirmation response that includes:
1. Confirmation that the form was created
2. Form details (title, date, location)
3. Form URL
4. What fields are included
5. Next steps or suggestions
"""

        # Check if client is available
        if not self.client:
            return f"""Perfect! I've created your signup form.

**Form Details:**
- **Title:** {form_data.get('title', 'Untitled Event')}
- **Date:** {form_data.get('event_date', 'TBD')}
- **Location:** {form_data.get('location', 'TBD')}

**Form URL:** {form_data.get('url', 'http://localhost:8000/forms/unknown')}

The form includes required fields for name, email, and phone number. Your form is now active and ready to accept registrations!

Note: LLM service is currently unavailable for generating custom responses."""

        try:
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=500,
                system=system_prompt,
                messages=[{"role": "user", "content": context}]
            )
            
            return response.content[0].text
            
        except Exception as e:
            # Fallback response with logging
            print(f"LLM API Error in form response: {e}", file=__import__('sys').stderr)
            return f"""Perfect! I've created your signup form.

**Form Details:**
- **Title:** {form_data.get('title', 'Untitled Event')}
- **Date:** {form_data.get('event_date', 'TBD')}
- **Location:** {form_data.get('location', 'TBD')}

**Form URL:** {form_data.get('url', 'http://localhost:8000/forms/unknown')}

The form includes required fields for name, email, and phone number. Your form is now active and ready to accept registrations!"""