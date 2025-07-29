"""Registration service for handling form submissions"""

import logging
import uuid
from typing import Optional

from ez_scheduler.models.registration import Registration
from ez_scheduler.models.signup_form import SignupForm
from sqlmodel import Session, select

logger = logging.getLogger(__name__)


class RegistrationService:
    """Service for managing user registrations"""

    def __init__(self, db_session: Session):
        self.db = db_session

    def create_registration(
        self,
        form_id: uuid.UUID,
        name: str,
        email: str,
        phone: str,
        user_id: Optional[uuid.UUID] = None,
        additional_data: Optional[dict] = None,
    ) -> Registration:
        """
        Create a new registration for a form.

        Args:
            form_id: UUID of the signup form
            name: User's name
            email: User's email address
            phone: User's phone number
            user_id: Optional user ID if user is authenticated
            additional_data: Optional additional form data

        Returns:
            Registration: The created registration

        Raises:
            ValueError: If the form doesn't exist or is inactive
        """
        # Verify form exists and is active
        form_stmt = select(SignupForm).where(
            SignupForm.id == form_id, SignupForm.is_active == True
        )
        form = self.db.exec(form_stmt).first()

        if not form:
            raise ValueError("Form not found or inactive")

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
