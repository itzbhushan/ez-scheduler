"""FormField service for managing custom form fields"""

import logging
import uuid
from typing import List

from sqlmodel import Session, select

from ez_scheduler.models.field_type import FieldType
from ez_scheduler.models.form_field import FormField

logger = logging.getLogger(__name__)


class FormFieldService:
    """Service for managing form fields"""

    def __init__(self, db_session: Session):
        self.db = db_session

    def create_form_fields(
        self, form_id: uuid.UUID, custom_fields: List[dict]
    ) -> List[FormField]:
        """
        Create multiple form fields for a signup form
        Note: This does NOT commit - caller must handle transaction

        Args:
            form_id: UUID of the signup form
            custom_fields: List of field dictionaries from LLM response

        Returns:
            List of created FormField instances
        """
        created_fields = []

        for i, field_data in enumerate(custom_fields):
            try:
                # Convert string field_type to enum
                field_type_str = field_data.get("field_type", "text")
                field_type_enum = FieldType(field_type_str)

                form_field = FormField(
                    form_id=form_id,
                    field_name=field_data.get("field_name"),
                    field_type=field_type_enum,
                    label=field_data.get("label"),
                    placeholder=field_data.get("placeholder"),
                    is_required=field_data.get("is_required", False),
                    options=field_data.get("options"),
                    field_order=field_data.get("field_order", i),
                )

                self.db.add(form_field)
                created_fields.append(form_field)

                logger.info(
                    f"Added form field '{form_field.field_name}' for form {form_id}"
                )

            except Exception as e:
                logger.error(f"Error creating form field {field_data}: {e}")
                raise

        logger.info(f"Prepared {len(created_fields)} form fields for creation")
        return created_fields

    def get_fields_by_form_id(self, form_id: uuid.UUID) -> List[FormField]:
        """
        Get all form fields for a specific form, ordered by field_order

        Args:
            form_id: UUID of the signup form

        Returns:
            List of FormField instances ordered by field_order
        """
        try:
            statement = (
                select(FormField)
                .where(FormField.form_id == form_id)
                .order_by(FormField.field_order)
            )
            result = self.db.exec(statement)
            fields = result.all()

            logger.info(f"Retrieved {len(fields)} form fields for form {form_id}")
            return fields

        except Exception as e:
            logger.error(f"Error retrieving form fields for form {form_id}: {e}")
            return []
