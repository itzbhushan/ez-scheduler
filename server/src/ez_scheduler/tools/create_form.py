"""Create Form Tool - Handles form creation conversations using LLM"""

import json
import logging
import re
import uuid
from datetime import date, datetime, time
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from ez_scheduler.auth.dependencies import UserClaims
from ez_scheduler.backends.llm_client import LLMClient
from ez_scheduler.config import config
from ez_scheduler.models.signup_form import SignupForm
from ez_scheduler.services.signup_form_service import SignupFormService
from ez_scheduler.system_prompts import FORM_BUILDER_PROMPT, FORM_RESPONSE_PROMPT

logger = logging.getLogger(__name__)


class FormExtractionSchema(BaseModel):
    """Schema for form extraction from user instructions"""

    title: Optional[str] = Field(None, description="Event title or name")
    event_date: Optional[str] = Field(None, description="Event date")
    start_time: Optional[str] = Field(
        None, description="Event start time in HH:MM format"
    )
    end_time: Optional[str] = Field(None, description="Event end time in HH:MM format")
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


async def create_form_handler(
    user: UserClaims,
    initial_request: str,
    llm_client: LLMClient,
    signup_form_service: SignupFormService,
) -> str:
    """
    Initiates form creation conversation.

    Args:
        user_id: User identifier (UUID)
        initial_request: Initial form creation request

    Returns:
        Response from the form creation process
    """

    logger.info(f"Creating form for user {user.user_id}: {initial_request}")

    # Create or continue conversation
    conversation_id = f"conv_{user.user_id}_{len(conversations) + 1}"

    if conversation_id not in conversations:
        conversations[conversation_id] = {
            "user_id": user.user_id,
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
        if extracted_data.start_time:
            conversation["form_data"]["start_time"] = extracted_data.start_time
        if extracted_data.end_time:
            conversation["form_data"]["end_time"] = extracted_data.end_time
        if extracted_data.location:
            conversation["form_data"]["location"] = extracted_data.location
        if extracted_data.description:
            conversation["form_data"]["description"] = extracted_data.description

        # Handle different actions
        if llm_response.action == "create_form" and extracted_data.is_complete:
            try:
                # Validate form data
                validate_form_data(conversation["form_data"])

                # Create form
                response_text = await _create_form(
                    conversation["form_data"],
                    llm_client,
                    signup_form_service,
                    conversation,
                )
            except ValueError as e:
                # Validation failed
                response_text = str(e)
                conversation["messages"].append(
                    {"role": "assistant", "content": response_text}
                )
                return response_text
            except Exception as e:
                # Form creation failed
                response_text = str(e)
                conversation["messages"].append(
                    {"role": "assistant", "content": response_text}
                )
                return response_text
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

    # Get current date for prompt context
    current_date = datetime.now().strftime("%Y-%m-%d")

    # Build conversation context
    context = f"""
CURRENT FORM DATA: {json.dumps(current_form_data, indent=2)}

CONVERSATION HISTORY:
{json.dumps(conversation_history[-5:], indent=2) if conversation_history else "No previous messages"}

USER MESSAGE: {user_message}
"""

    try:
        # Format the system prompt with current date
        system_prompt = FORM_BUILDER_PROMPT.format(current_date=current_date)

        response_text = await llm_client.process_instruction(
            messages=[{"role": "user", "content": context}],
            max_tokens=2000,
            system=system_prompt,
        )

        # Parse JSON response
        try:
            response_data = json.loads(response_text)
            return ConversationResponse(**response_data)
        except json.JSONDecodeError as e:
            # Log the actual response that failed to parse
            logger.error(f"JSON parsing failed for LLM response: {response_text}")
            logger.error(f"JSON parse error: {e}")
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


def validate_form_data(form_data: Dict[str, Any]) -> None:
    """
    Validate form data

    Args:
        form_data: Form data from conversation

    Raises:
        ValueError: If validation fails with descriptive error message
    """
    # Extract form fields
    title = form_data.get("title")
    event_date_str = form_data.get("event_date")
    location = form_data.get("location")
    description = form_data.get("description")

    # Check for missing required fields
    missing_fields = []
    if not title or title.strip() == "":
        missing_fields.append("event title")
    if not event_date_str or event_date_str in ["TBD", ""]:
        missing_fields.append("event date")
    if not location or location.strip() in ["TBD", ""]:
        missing_fields.append("event location")
    if not description or description.strip() == "":
        missing_fields.append("event description")

    if missing_fields:
        missing_list = ", ".join(missing_fields)
        raise ValueError(
            f"I need more information to create your form. Please provide: {missing_list}."
        )

    # Validate and parse event_date
    try:
        date.fromisoformat(event_date_str)
    except ValueError:
        raise ValueError(
            f"I couldn't understand the date '{event_date_str}'. Please provide the date in a clear format like 'January 15th, 2024' or '2024-01-15'."
        )


async def _create_form(
    form_data: Dict[str, Any],
    llm_client: LLMClient,
    signup_form_service: SignupFormService,
    conversation: Dict[str, Any],
) -> str:
    """
    Create a signup form with validated data

    Args:
        form_data: Form data from conversation (already validated)
        llm_client: LLM client for generating form ID and response
        signup_form_service: Service for database operations
        conversation: Conversation context

    Returns:
        Response message for the user

    Raises:
        Exception: If form creation fails
    """
    # Extract and clean form fields
    title = form_data["title"].strip()
    event_date_str = form_data["event_date"]
    start_time_str = form_data.get("start_time")
    end_time_str = form_data.get("end_time")
    location = form_data["location"].strip()
    description = form_data["description"].strip()

    # Parse event date
    event_date = date.fromisoformat(event_date_str)

    # Parse start and end times if provided
    start_time = None
    end_time = None

    if start_time_str:
        try:
            start_time = time.fromisoformat(start_time_str)
        except ValueError:
            logger.warning(f"Invalid start time format: {start_time_str}")

    if end_time_str:
        try:
            end_time = time.fromisoformat(end_time_str)
        except ValueError:
            logger.warning(f"Invalid end time format: {end_time_str}")

    # Generate meaningful form ID using LLM
    base_form_id = await generate_form_id(llm_client, title, event_date_str)

    # Add UUID to ensure uniqueness
    unique_id = str(uuid.uuid4())[:8]  # First 8 chars of UUID
    url_slug = f"{base_form_id}-{unique_id}"

    # Create form object
    signup_form = SignupForm(
        user_id=conversation["user_id"],
        title=title,
        event_date=event_date,
        start_time=start_time,
        end_time=end_time,
        location=location,
        description=description,
        url_slug=url_slug,
        is_active=True,
    )

    # Create form in database
    result = signup_form_service.create_signup_form(signup_form)

    if not result["success"]:
        raise Exception(
            f"I encountered an error creating your form: {result['error']}. Please try again."
        )

    # Update conversation
    conversation["status"] = "completed"
    conversation["form_id"] = result["form_id"]

    # Use LLM to generate response with dynamic URL
    form_data_with_url = {
        "id": result["form_id"],
        "title": title,
        "event_date": event_date_str,
        "location": location,
        "description": description,
        "url_slug": url_slug,
        "url": f"{config['app_base_url']}/form/{url_slug}",
    }

    try:
        return await generate_form_response(llm_client, form_data_with_url)
    except Exception as e:
        logger.error(f"Error generating form response: {e}")
        # Fallback response
        return f"We could not generate a form. Please retry later."
