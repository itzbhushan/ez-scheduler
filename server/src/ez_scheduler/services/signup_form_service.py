"""SignupForm Service - Handles signup form database operations"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlmodel import Session, select

from ez_scheduler.auth.models import User
from ez_scheduler.models.signup_form import SignupForm

logger = logging.getLogger(__name__)


class SignupFormService:
    """Service for handling signup form operations"""

    def __init__(self, db_session: Session):
        self.db = db_session

    def create_signup_form(
        self, signup_form: SignupForm, user: Optional[User] = None
    ) -> Dict[str, Any]:
        """
        Create a new signup form in the database

        Args:
            signup_form: SignupForm object to create

        Returns:
            Dictionary containing creation result and form details
        """
        try:
            # Ensure timestamps are set
            if not signup_form.created_at:
                signup_form.created_at = datetime.now(timezone.utc)
            if not signup_form.updated_at:
                signup_form.updated_at = datetime.now(timezone.utc)
            if not signup_form.id:
                signup_form.id = uuid.uuid4()

            self.db.add(signup_form)
            self.db.commit()
            self.db.refresh(signup_form)

            logger.info(f"Signup form created successfully: {signup_form.id}")

            return {
                "success": True,
                "form_id": str(signup_form.id),
                "url_slug": signup_form.url_slug,
                "message": "Signup form created successfully",
                "created_at": signup_form.created_at.isoformat(),
            }

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating signup form: {e}")
            return {
                "success": False,
                "error": f"Failed to create signup form: {str(e)}",
                "form_id": None,
            }

    def update_signup_form(
        self, form_id: uuid.UUID, updated_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update an existing signup form

        Args:
            form_id: UUID of the signup form to update
            updated_data: Dictionary containing updated form data

        Returns:
            Dictionary containing update result
        """
        try:
            signup_form = self.db.get(SignupForm, form_id)

            if not signup_form:
                return {"success": False, "error": "Signup form not found"}

            # Update form fields
            if "title" in updated_data:
                signup_form.title = updated_data["title"]
            if "event_date" in updated_data:
                signup_form.event_date = updated_data["event_date"]
            if "start_time" in updated_data:
                signup_form.start_time = updated_data["start_time"]
            if "end_time" in updated_data:
                signup_form.end_time = updated_data["end_time"]
            if "location" in updated_data:
                signup_form.location = updated_data["location"]
            if "description" in updated_data:
                signup_form.description = updated_data["description"]
            if "url_slug" in updated_data:
                signup_form.url_slug = updated_data["url_slug"]
            if "is_active" in updated_data:
                signup_form.is_active = updated_data["is_active"]

            signup_form.updated_at = datetime.now(timezone.utc)

            self.db.add(signup_form)
            self.db.commit()
            self.db.refresh(signup_form)

            logger.info(f"Signup form updated successfully: {signup_form.id}")

            return {
                "success": True,
                "form_id": str(signup_form.id),
                "message": "Signup form updated successfully",
            }

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating signup form {form_id}: {e}")
            return {
                "success": False,
                "error": f"Failed to update signup form: {str(e)}",
            }

    def get_form_by_url_slug(self, url_slug: str) -> Optional[SignupForm]:
        """
        Retrieve an active signup form by its URL slug

        Args:
            url_slug: URL slug of the signup form to retrieve

        Returns:
            SignupForm object if found and active, None otherwise
        """
        try:
            logger.info(f"Retrieving signup form by URL slug: {url_slug}")
            statement = select(SignupForm).where(
                SignupForm.url_slug == url_slug, SignupForm.is_active == True
            )
            form = self.db.execute(statement).scalar_one_or_none()
            return form
        except Exception as e:
            logger.error(f"Error retrieving signup form by URL slug {url_slug}: {e}")
            return None

    def delete_signup_form(self, form_id: uuid.UUID) -> Dict[str, Any]:
        """
        Delete a signup form (soft delete by setting is_active to False)

        Args:
            form_id: UUID of the signup form to delete

        Returns:
            Dictionary containing deletion result
        """
        try:
            signup_form = self.db.get(SignupForm, form_id)

            if not signup_form:
                return {"success": False, "error": "Signup form not found"}

            # Soft delete by setting is_active to False
            signup_form.is_active = False
            signup_form.updated_at = datetime.now(timezone.utc)

            self.db.add(signup_form)
            self.db.commit()

            logger.info(f"Signup form deleted (deactivated) successfully: {form_id}")

            return {"success": True, "message": "Signup form deleted successfully"}

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error deleting signup form {form_id}: {e}")
            return {
                "success": False,
                "error": f"Failed to delete signup form: {str(e)}",
            }
