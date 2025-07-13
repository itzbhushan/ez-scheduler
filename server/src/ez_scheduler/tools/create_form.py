"""Create Form Tool - Handles form creation conversations using LLM"""

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from ..llm_client import LLMClient
from ..system_prompts import FORM_BUILDER_PROMPT, FORM_RESPONSE_PROMPT

logger = logging.getLogger(__name__)


class FormExtractionSchema(BaseModel):
    """Schema for form extraction from user instructions"""

    title: Optional[str] = Field(None, description="Event title or name")
    event_date: Optional[str] = Field(None, description="Event date")
    location: Optional[str] = Field(None, description="Event location")
    description: Optional[str] = Field(None, description="Event description")
    additional_fields: Optional[list] = Field(
        default_factory=list, description="Additional form fields requested"
    )
    is_complete: bool = Field(False, description="Whether all required info is present")
    next_question: Optional[str] = Field(
        None, description="Next question to ask user if not complete"
    )


class ConversationResponse(BaseModel):
    """Schema for conversation responses"""

    response_text: str = Field(..., description="Response to send to user")
    extracted_data: FormExtractionSchema = Field(..., description="Extracted form data")
    action: str = Field(
        ..., description="Action to take: 'continue', 'create_form', 'clarify'"
    )


# Global storage - shared across the application
conversations: Dict[str, Dict[str, Any]] = {}
forms: Dict[str, Dict[str, Any]] = {}


async def create_form_handler(
    user_id: str, initial_request: str, llm_client: LLMClient
) -> str:
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
            "form_data": {},
        }

    # Add user message
    conversations[conversation_id]["messages"].append(
        {"role": "user", "content": initial_request}
    )

    # Process conversation using LLM
    conversation = conversations[conversation_id]

    try:
        # Use LLM to process the instruction
        llm_response = await process_form_instruction(
            llm_client=llm_client,
            user_message=initial_request,
            conversation_history=conversation["messages"],
            current_form_data=conversation["form_data"],
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
            base_form_id = await generate_form_id(llm_client, title, event_date)

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
                    {
                        "name": "name",
                        "type": "text",
                        "required": True,
                        "label": "Full Name",
                    },
                    {
                        "name": "email",
                        "type": "email",
                        "required": True,
                        "label": "Email Address",
                    },
                    {
                        "name": "phone",
                        "type": "tel",
                        "required": True,
                        "label": "Phone Number",
                    },
                ],
            }

            conversation["status"] = "completed"
            conversation["form_id"] = form_id

            # Use LLM to generate response with dynamic URL
            form_data_with_url = forms[form_id].copy()
            form_data_with_url["url"] = f"http://localhost:8000/forms/{form_id}"
            response_text = await generate_form_response(llm_client, form_data_with_url)
        else:
            response_text = llm_response.response_text

        # Add assistant response
        conversation["messages"].append({"role": "assistant", "content": response_text})

        return response_text

    except Exception as e:
        logger.error(f"Error processing form creation: {e}")
        error_response = "I'm experiencing technical difficulties. Please try again."

        conversation["messages"].append(
            {"role": "assistant", "content": error_response}
        )

        return error_response


async def process_form_instruction(
    llm_client: LLMClient,
    user_message: str,
    conversation_history: list = None,
    current_form_data: Dict[str, Any] = None,
) -> ConversationResponse:
    """Process user instruction for form creation/modification"""

    conversation_history = conversation_history or []
    current_form_data = current_form_data or {}

    # Build conversation context
    context = f"""
CURRENT FORM DATA: {json.dumps(current_form_data, indent=2)}

CONVERSATION HISTORY:
{json.dumps(conversation_history[-5:], indent=2) if conversation_history else "No previous messages"}

USER MESSAGE: {user_message}
"""

    try:
        response_text = await llm_client.process_instruction(
            messages=[{"role": "user", "content": context}],
            max_tokens=1000,
            system=FORM_BUILDER_PROMPT,
        )

        # Parse JSON response
        try:
            response_data = json.loads(response_text)
            return ConversationResponse(**response_data)
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            return ConversationResponse(
                response_text="I'm having trouble processing your request. Could you please rephrase it?",
                extracted_data=FormExtractionSchema(),
                action="clarify",
            )

    except Exception as e:
        # Error handling with logging
        logger.error(f"LLM API Error: {e}")
        return ConversationResponse(
            response_text="I'm experiencing technical difficulties. Please try again.",
            extracted_data=FormExtractionSchema(),
            action="clarify",
        )


async def generate_form_response(
    llm_client: LLMClient, form_data: Dict[str, Any]
) -> str:
    """Generate a form creation confirmation response"""

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

    try:
        return await llm_client.process_instruction(
            messages=[{"role": "user", "content": context}],
            max_tokens=500,
            system=FORM_RESPONSE_PROMPT,
        )

    except Exception as e:
        # Fallback response with logging
        logger.error(f"LLM API Error in form response: {e}")
        raise ValueError("Failed to generate form response. Please try again later.")


async def generate_form_id(llm_client: LLMClient, title: str, event_date: str) -> str:
    """Generate a meaningful form ID using LLM based on event details"""
    try:
        # Ask LLM to generate a URL-friendly form ID
        prompt = f"""Generate a short, URL-friendly form ID (slug) for an event form.

Event Details:
- Title: {title}
- Date: {event_date}

Requirements:
- Use lowercase letters, numbers, and hyphens only
- Maximum 30 characters
- Be descriptive but concise
- Include year if available in date
- Remove special characters and spaces

Examples:
- "John's Birthday Party" on "March 15th, 2025" → "johns-birthday-party-2025"
- "Company Retreat" on "July 2024" → "company-retreat-2024"
- "Wedding Reception" on "December 12th" → "wedding-reception-dec"

Generate only the form ID, no explanation:"""

        response_text = await llm_client.process_instruction(
            messages=[{"role": "user", "content": prompt}], max_tokens=50
        )

        generated_id = response_text.strip().lower()
        # Clean and validate the generated ID
        generated_id = re.sub(r"[^a-z0-9-]", "", generated_id)
        generated_id = re.sub(
            r"-+", "-", generated_id
        )  # Remove multiple consecutive hyphens
        generated_id = generated_id.strip("-")  # Remove leading/trailing hyphens

        if len(generated_id) > 30:
            generated_id = generated_id[:30].rstrip("-")

        # If empty or too short, use fallback
        if len(generated_id) < 3:
            return _fallback_form_id(title, event_date)

        return generated_id

    except Exception as e:
        logger.error(f"Failed to generate form ID with LLM: {e}")
        return _fallback_form_id(title, event_date)


def _fallback_form_id(title: str, event_date: str) -> str:
    """Fallback form ID generation without LLM"""
    # Simple slug generation
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9\s]", "", slug)  # Remove special chars
    slug = re.sub(r"\s+", "-", slug)  # Replace spaces with hyphens
    slug = slug.strip("-")  # Remove leading/trailing hyphens

    # Add year if found in date
    year_match = re.search(r"20\d{2}", event_date)
    if year_match:
        slug += f"-{year_match.group()}"

    # Limit length
    if len(slug) > 30:
        slug = slug[:30].rstrip("-")

    return slug if slug else "event"
