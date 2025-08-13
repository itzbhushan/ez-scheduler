"""User Service - Handles user database operations"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ez_scheduler.models.user import User
from sqlmodel import Session, select

logger = logging.getLogger(__name__)


class UserService:
    """Service for handling user operations"""

    def __init__(self, db_session: Session):
        self.db = db_session

    def create_user(self, email: str, name: str) -> User:
        """
        Create a new user in the database

        Args:
            email: User's email address (must be unique)
            name: User's display name

        Returns:
            Created User object

        Raises:
            Exception: If user creation fails
        """
        try:
            # Create user object - SQLModel will auto-generate UUID
            user = User(email=email, name=name, is_active=True)

            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)

            logger.info(f"User created successfully: {user.id}")

            return user

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error creating user: {e}")
            raise Exception(f"Failed to create user: {str(e)}")

    def get_user_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        """
        Get a user by their ID

        Args:
            user_id: UUID of the user to retrieve

        Returns:
            User object if found, None otherwise
        """
        try:
            user = self.db.get(User, user_id)
            return user
        except Exception as e:
            logger.error(f"Error retrieving user {user_id}: {e}")
            return None

    def get_user_by_email(self, email: str) -> Optional[User]:
        """
        Get a user by their email address

        Args:
            email: Email address to search for

        Returns:
            User object if found, None otherwise
        """
        try:
            statement = select(User).where(User.email == email)
            user = self.db.exec(statement).first()
            return user
        except Exception as e:
            logger.error(f"Error retrieving user by email {email}: {e}")
            return None

    def update_user(
        self, user_id: uuid.UUID, updated_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update an existing user

        Args:
            user_id: UUID of the user to update
            updated_data: Dictionary containing updated user data

        Returns:
            Dictionary containing update result
        """
        try:
            user = self.db.get(User, user_id)

            if not user:
                return {"success": False, "error": "User not found"}

            # Update user fields
            if "email" in updated_data:
                user.email = updated_data["email"]
            if "name" in updated_data:
                user.name = updated_data["name"]
            if "is_active" in updated_data:
                user.is_active = updated_data["is_active"]

            user.updated_at = datetime.now(timezone.utc)

            self.db.add(user)
            self.db.commit()
            self.db.refresh(user)

            logger.info(f"User updated successfully: {user.id}")

            return {
                "success": True,
                "user_id": str(user.id),
                "message": "User updated successfully",
            }

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error updating user {user_id}: {e}")
            return {"success": False, "error": f"Failed to update user: {str(e)}"}

    def delete_user(self, user_id: uuid.UUID) -> Dict[str, Any]:
        """
        Soft delete a user (set is_active to False)

        Args:
            user_id: UUID of the user to delete

        Returns:
            Dictionary containing deletion result
        """
        try:
            user = self.db.get(User, user_id)

            if not user:
                return {"success": False, "error": "User not found"}

            # Soft delete by setting is_active to False
            user.is_active = False
            user.updated_at = datetime.now(timezone.utc)

            self.db.add(user)
            self.db.commit()

            logger.info(f"User soft deleted successfully: {user_id}")

            return {"success": True, "message": "User deleted successfully"}

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error deleting user {user_id}: {e}")
            return {"success": False, "error": f"Failed to delete user: {str(e)}"}
