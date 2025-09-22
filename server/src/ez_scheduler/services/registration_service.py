"""Registration service for handling form submissions"""

import logging
import uuid
from typing import Optional

from sqlmodel import Session, select

from ez_scheduler.backends.llm_client import LLMClient
from ez_scheduler.models.registration import Registration
from ez_scheduler.models.signup_form import FormStatus, SignupForm
from ez_scheduler.system_prompts import CONFIRMATION_MESSAGE_PROMPT

logger = logging.getLogger(__name__)


class RegistrationService:
    """Service for managing user registrations"""

    def __init__(self, db_session: Session, llm_client: LLMClient):
        self.db = db_session
        self.llm_client = llm_client

    def create_registration(
        self,
        form_id: uuid.UUID,
        name: str,
        email: str,
        phone: str,
        user_id: Optional[str] = None,
        additional_data: Optional[dict] = None,
    ) -> Registration:
        """
        Create a new registration for a form.

        Args:
            form_id: UUID of the signup form
            name: User's name
            email: User's email address
            phone: User's phone number
            user_id: Optional Auth0 user ID string if user is authenticated
            additional_data: Optional additional form data

        Returns:
            Registration: The created registration

        Raises:
            ValueError: If the form doesn't exist or is inactive
        """
        # Verify form exists and is published
        form_stmt = select(SignupForm).where(
            SignupForm.id == form_id,
            SignupForm.status == FormStatus.PUBLISHED,
        )
        form = self.db.exec(form_stmt).first()

        if not form:
            raise ValueError("Form not found or not published")

        registration = Registration(
            form_id=form_id,
            user_id=user_id,
            name=name,
            email=email,
            phone=phone,
            additional_data=additional_data,
        )

        self.db.add(registration)
        self.db.commit()
        self.db.refresh(registration)

        logger.info(f"Created registration {registration.id} for form {form_id}")
        return registration

    def get_registration_by_id(
        self, registration_id: uuid.UUID
    ) -> Optional[Registration]:
        """Get a registration by ID"""
        stmt = select(Registration).where(Registration.id == registration_id)
        return self.db.exec(stmt).first()

    def get_registrations_for_form(self, form_id: uuid.UUID) -> list[Registration]:
        """Get all registrations for a specific form"""
        stmt = select(Registration).where(Registration.form_id == form_id)
        return list(self.db.exec(stmt).all())

    def get_registration_count_for_form(self, form_id: uuid.UUID) -> int:
        """Get the total number of registrations for a form"""
        stmt = select(Registration).where(Registration.form_id == form_id)
        return len(list(self.db.exec(stmt).all()))

    async def generate_confirmation_message(
        self, form, registrant_name: str, rsvp_response: str = None
    ) -> str:
        """Generate a personalized confirmation message using LLM"""
        try:

            # User message with event context
            user_message = f"""Generate a confirmation message for this registration:

Event: {form.title}
Date: {form.event_date}
Time: {form.start_time.strftime('%I:%M %p') if form.start_time else 'TBD'} - {form.end_time.strftime('%I:%M %p') if form.end_time else 'TBD'}
Location: {form.location}
Description: {form.description if form.description else 'No description provided'}

Registrant: {registrant_name}
RSVP Response: {rsvp_response if rsvp_response else 'attending'}

Generate just the confirmation message, nothing else."""

            messages = [{"role": "user", "content": user_message}]

            response = await self.llm_client.process_instruction(
                messages=messages, system=CONFIRMATION_MESSAGE_PROMPT, max_tokens=150
            )
            return response.strip()

        except Exception as e:
            logger.warning(f"Failed to generate LLM confirmation message: {e}")
            # Fallback to a simple personalized message
            return f"Thanks for registering for {form.title}, {registrant_name}! We're excited to see you there."
