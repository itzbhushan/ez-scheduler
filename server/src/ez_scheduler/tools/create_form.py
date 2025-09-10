"""Create Form Tool - Handles form creation conversations using LLM"""

import json
import logging
import re
import uuid
from datetime import date, datetime, time, timezone
from typing import List, Optional

from pydantic import BaseModel, Field

from ez_scheduler.auth.dependencies import User
from ez_scheduler.backends.llm_client import LLMClient
from ez_scheduler.config import config
from ez_scheduler.models.enums import FieldType
from ez_scheduler.models.signup_form import SignupForm
from ez_scheduler.services.form_field_service import FormFieldService
from ez_scheduler.services.signup_form_service import SignupFormService
from ez_scheduler.system_prompts import FORM_BUILDER_PROMPT, FORM_RESPONSE_PROMPT

logger = logging.getLogger(__name__)


class CustomFieldSchema(BaseModel):
    """Schema for custom form fields"""

    field_name: str = Field(
        ..., description="Internal field name (e.g., 'guest_count')"
    )
    field_type: FieldType = Field(
        ..., description="Field type: text, number, select, or checkbox"
    )
    label: str = Field(..., description="Display label for the field")
    placeholder: Optional[str] = Field(None, description="Placeholder text for input")
    is_required: bool = Field(default=False, description="Whether field is required")
    options: Optional[List[str]] = Field(None, description="Options for select fields")
    field_order: Optional[int] = Field(None, description="Display order")


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
    custom_fields: List[CustomFieldSchema] = Field(
        default_factory=list, description="Custom form fields beyond name/email/phone"
    )
    is_complete: bool = Field(False, description="Whether all required info is present")
    next_question: Optional[str] = Field(
        None, description="Next question to ask user if not complete"
    )
    form_url: Optional[str] = Field(None, description="Generated form URL")
    form_id: Optional[str] = Field(None, description="Database form ID")


class ConversationResponse(BaseModel):
    """Schema for conversation responses"""

    response_text: str = Field(..., description="Response to send to user")
    extracted_data: FormExtractionSchema = Field(..., description="Extracted form data")
    action: str = Field(
        ..., description="Action to take: 'continue', 'create_form', 'clarify'"
    )


async def create_form_handler(
    user: User,
    initial_request: str,
    llm_client: LLMClient,
    signup_form_service: SignupFormService,
) -> str:
    """
    Initiates form creation conversation.

    Args:
        user: User object
        initial_request: Initial form creation request
        llm_client: LLM client for processing
        signup_form_service: Service for form operations

    Returns:
        Response from the form creation process
    """

    logger.info(f"Creating form for user {user.user_id}: {initial_request}")

    try:
        # Process the form instruction directly with LLM
        llm_response = await process_form_instruction(
            llm_client=llm_client,
            user_message=initial_request,
        )

        # Use extracted data directly (no conversion needed)
        extracted_data = llm_response.extracted_data

        # Handle different actions
        if llm_response.action == "create_form" and extracted_data.is_complete:
            try:
                # Validate form data
                _validate_form_data(extracted_data)

                # Create form
                response_text = await _create_form(
                    extracted_data,
                    llm_client,
                    signup_form_service,
                    user,
                )
            except ValueError as e:
                # Validation failed - return validation error
                return str(e)
            except Exception as e:
                # Form creation failed
                return str(e)
        else:
            response_text = llm_response.response_text

        return response_text

    except Exception as e:
        logger.error(f"Error processing form creation: {e}")
        return "I'm experiencing technical difficulties. Please try again."


async def process_form_instruction(
    llm_client: LLMClient,
    user_message: str,
) -> ConversationResponse:
    """Process user instruction for form creation/modification"""

    # Get current date for prompt context
    current_date = datetime.now().strftime("%Y-%m-%d")

    try:
        # Format the system prompt with current date
        system_prompt = FORM_BUILDER_PROMPT.format(current_date=current_date)

        response_text = await llm_client.process_instruction(
            messages=[{"role": "user", "content": user_message}],
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
    llm_client: LLMClient, form_data: FormExtractionSchema
) -> str:
    """Generate a form creation confirmation response"""

    context = f"""
FORM CREATED:
- Title: {form_data.title}
- Date: {form_data.event_date}
- Start Time: {form_data.start_time or 'Not specified'}
- End Time: {form_data.end_time or 'Not specified'}
- Location: {form_data.location}
- Description: {form_data.description}
- Form URL: {form_data.form_url}
- Form ID: {form_data.form_id}

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
- "John's Birthday Party" on "March 15th, 2025" → "johns-birthday-march-15-25"
- "Company Retreat" on "July 2024" → "company-retreat-july-2024"
- "Wedding Reception" on "December 12th" → "wedding-reception-dec-12"

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


def _validate_form_data(form_data: FormExtractionSchema) -> None:
    """
    Validate form data

    Args:
        form_data: FormExtractionSchema instance

    Raises:
        ValueError: If validation fails with descriptive error message
    """
    # Check for missing required fields
    missing_fields = []
    if not form_data.title or form_data.title.strip() == "":
        missing_fields.append("event title")
    if not form_data.event_date or form_data.event_date in ["TBD", ""]:
        missing_fields.append("event date")
    if not form_data.location or form_data.location.strip() in ["TBD", ""]:
        missing_fields.append("event location")
    if not form_data.description or form_data.description.strip() == "":
        missing_fields.append("event description")

    if missing_fields:
        missing_list = ", ".join(missing_fields)
        raise ValueError(
            f"I need more information to create your form. Please provide: {missing_list}."
        )

    # Validate and parse event_date
    try:
        date.fromisoformat(form_data.event_date)
    except ValueError:
        raise ValueError(
            f"I couldn't understand the date '{form_data.event_date}'. Please provide the date in a clear format like 'January 15th, 2024' or '2024-01-15'."
        )


async def _create_form(
    form_data: FormExtractionSchema,
    llm_client: LLMClient,
    signup_form_service: SignupFormService,
    user: User,
) -> str:
    """
    Create a signup form with validated data and custom fields

    Args:
        form_data: FormExtractionSchema instance (already validated)
        llm_client: LLM client for generating form ID and response
        signup_form_service: Service for database operations
        user: User object

    Returns:
        Response message for the user

    Raises:
        Exception: If form creation fails
    """
    # Extract and clean form fields
    title = form_data.title.strip()
    event_date_str = form_data.event_date
    start_time_str = form_data.start_time
    end_time_str = form_data.end_time
    location = form_data.location.strip()
    description = form_data.description.strip()

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
        user_id=user.user_id,
        title=title,
        event_date=event_date,
        start_time=start_time,
        end_time=end_time,
        location=location,
        description=description,
        url_slug=url_slug,
        is_active=True,
    )

    # Create form and custom fields in a single transaction
    try:
        # Use the database session directly for transaction control
        db_session = signup_form_service.db

        # Set form ID and timestamps
        if not signup_form.id:
            signup_form.id = uuid.uuid4()
        if not signup_form.created_at:
            signup_form.created_at = datetime.now(timezone.utc)
        if not signup_form.updated_at:
            signup_form.updated_at = datetime.now(timezone.utc)

        # Add signup form to session and flush to get the ID in database
        db_session.add(signup_form)
        db_session.flush()  # This writes the form to DB but doesn't commit the transaction

        # Create custom fields if any
        if form_data.custom_fields:
            form_field_service = FormFieldService(db_session)

            # Convert CustomFieldSchema objects to dictionaries
            custom_fields_data = [
                {
                    "field_name": field.field_name,
                    "field_type": field.field_type,
                    "label": field.label,
                    "placeholder": field.placeholder,
                    "is_required": field.is_required,
                    "options": field.options,
                    "field_order": (
                        field.field_order if field.field_order is not None else i
                    ),
                }
                for i, field in enumerate(form_data.custom_fields)
            ]

            form_field_service.create_form_fields(signup_form.id, custom_fields_data)

        # Commit the entire transaction
        db_session.commit()
        db_session.refresh(signup_form)

        logger.info(
            f"Created signup form {signup_form.id} with {len(form_data.custom_fields)} custom fields"
        )

    except Exception as e:
        db_session.rollback()
        logger.error(f"Error creating form with custom fields: {e}")
        raise Exception(
            f"I encountered an error creating your form: {str(e)}. Please try again."
        )

    # Set form URL and ID in the FormData
    form_data.form_url = f"{config['app_base_url']}/form/{url_slug}"
    form_data.form_id = str(signup_form.id)

    try:
        return await generate_form_response(llm_client, form_data)
    except Exception as e:
        logger.error(f"Error generating form response: {e}")
        # Fallback response
        return f"We could not generate a form. Please retry later."
