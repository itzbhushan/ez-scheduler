"""Create or Update Form Tool - Unified conversational form builder"""

import logging
import re
import uuid
from datetime import date, time
from typing import Any, Dict

from ez_scheduler.auth.models import User
from ez_scheduler.backends.llm_client import LLMClient
from ez_scheduler.config import config
from ez_scheduler.handlers.form_conversation_handler import FormConversationHandler
from ez_scheduler.models.signup_form import FormStatus, SignupForm
from ez_scheduler.services.conversation_manager import ConversationManager
from ez_scheduler.services.form_field_service import FormFieldService
from ez_scheduler.services.form_state_manager import FormStateManager
from ez_scheduler.services.signup_form_service import SignupFormService
from ez_scheduler.services.timeslot_service import TimeslotSchedule, TimeslotService

logger = logging.getLogger(__name__)


class CreateOrUpdateFormTool:
    """
    Unified conversational form creation/update tool.

    This tool manages the entire conversation flow:
    - Auto-detects active conversation thread
    - Maintains conversation history and form state in Redis
    - Processes messages through FormConversationHandler
    - Automatically creates or updates drafts when LLM marks form complete
    - Transparently handles create vs update based on form_id presence
    """

    def __init__(
        self,
        llm_client: LLMClient,
        conversation_manager: ConversationManager,
        form_state_manager: FormStateManager,
        signup_form_service: SignupFormService,
        form_field_service: FormFieldService,
    ):
        """
        Initialize CreateOrUpdateFormTool.

        Args:
            llm_client: LLM client for processing
            conversation_manager: Manages conversation history
            form_state_manager: Manages form state in Redis
            signup_form_service: Service for form database operations
            form_field_service: Service for form field operations
        """
        self.llm_client = llm_client
        self.conversation_manager = conversation_manager
        self.form_state_manager = form_state_manager
        self.signup_form_service = signup_form_service
        self.form_field_service = form_field_service

    async def execute(self, user: User, message: str) -> str:
        """
        Execute the create or update form conversation.

        Args:
            user: User object with user_id and claims
            message: User's message in the conversation

        Returns:
            Natural language response to user
        """
        logger.info(f"Processing form message for user {user.user_id}: {message}")

        try:
            # Step 1: Auto-detect or create conversation thread
            thread_id = self.conversation_manager.get_or_create_thread_for_user(
                user.user_id
            )
            logger.info(f"Using thread {thread_id} for user {user.user_id}")

            # Step 2: Initialize conversation handler
            handler = FormConversationHandler(
                llm_client=self.llm_client,
                conversation_manager=self.conversation_manager,
                form_state_manager=self.form_state_manager,
            )

            # Step 3: Process message with conversation context
            response = await handler.process_message(
                user=user, thread_id=thread_id, user_message=message
            )

            # Step 4: Check if form is complete (LLM-determined)
            if response.is_complete:
                logger.info(f"Form marked complete by LLM for thread {thread_id}")

                # Step 5: Check for existing form_id in state
                form_id_str = response.form_state.get("form_id")

                if form_id_str:
                    # UPDATE existing draft
                    logger.info(f"Updating existing draft: {form_id_str}")
                    try:
                        form_id = uuid.UUID(form_id_str)
                        return await self._update_existing_draft(
                            form_id=form_id,
                            form_state=response.form_state,
                            user=user,
                        )
                    except Exception as e:
                        logger.error(f"Failed to update draft {form_id_str}: {e}")
                        return f"I encountered an error updating your form: {str(e)}. Please try again."
                else:
                    # CREATE new draft (keep thread alive for updates)
                    logger.info(f"Creating new draft for thread {thread_id}")
                    try:
                        return await self._create_draft_form(
                            form_state=response.form_state,
                            thread_id=thread_id,
                            user=user,
                        )
                    except Exception as e:
                        logger.error(f"Failed to create draft: {e}")
                        return f"I encountered an error creating your form: {str(e)}. Please try again."
            else:
                # Continue conversation - not yet complete
                logger.info(f"Conversation continues for thread {thread_id}")
                return response.response_text

        except Exception as e:
            logger.error(f"Error in create_or_update_form tool: {e}")
            return "I'm experiencing technical difficulties. Please try again."

    async def _create_draft_form(
        self,
        form_state: Dict[str, Any],
        thread_id: str,
        user: User,
    ) -> str:
        """
        Create a new draft form from conversation state.

        Args:
            form_state: Complete form state from FormConversationHandler
            thread_id: Conversation thread ID
            user: User object

        Returns:
            Response message with preview URL
        """
        # Validate required fields
        required_fields = ["title", "event_date", "location", "description"]
        missing = [f for f in required_fields if not form_state.get(f)]
        if missing:
            raise ValueError(
                f"Missing required fields for form creation: {', '.join(missing)}"
            )

        # Parse and validate data
        try:
            event_date = date.fromisoformat(form_state["event_date"])
        except (ValueError, KeyError) as e:
            raise ValueError(f"Invalid event_date: {e}")

        # Parse optional times
        start_time = None
        end_time = None
        if form_state.get("start_time"):
            try:
                start_time = time.fromisoformat(form_state["start_time"])
            except ValueError:
                logger.warning(f"Invalid start_time: {form_state.get('start_time')}")

        if form_state.get("end_time"):
            try:
                end_time = time.fromisoformat(form_state["end_time"])
            except ValueError:
                logger.warning(f"Invalid end_time: {form_state.get('end_time')}")

        # Generate URL slug
        url_slug = await self._generate_url_slug(
            title=form_state["title"],
            event_date=form_state["event_date"],
        )

        # Extract button configuration
        button_config = form_state.get("button_config", {})
        button_type = button_config.get("button_type", "single_submit")
        primary_button_text = button_config.get("primary_button_text", "Register")
        secondary_button_text = button_config.get("secondary_button_text")

        # Create SignupForm object
        signup_form = SignupForm(
            user_id=user.user_id,
            title=form_state["title"],
            event_date=event_date,
            start_time=start_time,
            end_time=end_time,
            location=form_state["location"],
            description=form_state.get("description"),
            url_slug=url_slug,
            status=FormStatus.DRAFT,
            button_type=button_type,
            primary_button_text=primary_button_text,
            secondary_button_text=secondary_button_text,
        )

        # Prepare custom fields
        custom_fields = form_state.get("custom_fields", [])
        custom_fields_data = [
            {
                "field_name": field.get("field_name"),
                "field_type": field.get("field_type"),
                "label": field.get("label"),
                "placeholder": field.get("placeholder"),
                "is_required": field.get("is_required", False),
                "options": field.get("options"),
                "field_order": field.get("field_order", i),
            }
            for i, field in enumerate(custom_fields)
        ]

        # Parse timeslot schedule if present
        timeslot_schedule = None
        if form_state.get("timeslot_schedule"):
            try:
                schedule_dict = dict(form_state["timeslot_schedule"])
                # Convert start_from_date string to date object if present
                if schedule_dict.get("start_from_date"):
                    try:
                        schedule_dict["start_from_date"] = date.fromisoformat(
                            schedule_dict["start_from_date"]
                        )
                    except ValueError:
                        schedule_dict.pop("start_from_date", None)

                timeslot_schedule = TimeslotSchedule(**schedule_dict)
            except (TypeError, ValueError) as e:
                logger.warning(f"Failed to parse timeslot_schedule: {e}")

        # Create form with all details
        try:
            created_form = self.signup_form_service.create_signup_form_with_details(
                signup_form=signup_form,
                custom_fields=custom_fields_data,
                timeslot_schedule=timeslot_schedule,
            )
        except Exception as e:
            raise Exception(f"Failed to create form in database: {e}")

        # Store form_id in conversation state for future updates
        self.form_state_manager.update_state(
            thread_id, {"form_id": str(created_form.id)}
        )
        logger.info(
            f"Created draft form {created_form.id}, stored in thread {thread_id}"
        )

        # Generate preview URL
        preview_url = f"{config['app_base_url']}/form/{created_form.url_slug}"

        # Return success response
        return (
            f"Great! I've created your draft form.\n\n"
            f"**{created_form.title}**\n"
            f"📅 {event_date.strftime('%B %d, %Y')}\n"
            f"📍 {created_form.location}\n\n"
            f"Preview your form: {preview_url}\n\n"
            f"You can continue to modify it by telling me what to change, "
            f"or say 'publish the form' when you're ready!"
        )

    async def _update_existing_draft(
        self,
        form_id: uuid.UUID,
        form_state: Dict[str, Any],
        user: User,
    ) -> str:
        """
        Update an existing draft form from conversation state.

        Args:
            form_id: UUID of existing form
            form_state: Updated form state from FormConversationHandler
            user: User object

        Returns:
            Response message with preview URL
        """
        # Get existing form
        try:
            existing_form = self.signup_form_service.get_form_by_id(form_id)
        except Exception as e:
            raise ValueError(f"Form not found: {e}")

        if not existing_form:
            raise ValueError("Form not found")

        # Verify ownership
        if existing_form.user_id != user.user_id:
            raise ValueError("You don't have permission to update this form")

        # Verify form is still a draft (only drafts can be updated)
        if existing_form.status == FormStatus.PUBLISHED:
            raise ValueError(
                "Published forms cannot be updated. Please create a new form or unpublish this one first."
            )
        if existing_form.status == FormStatus.ARCHIVED:
            raise ValueError("Archived forms cannot be updated")

        # Build update payload
        updated_data: Dict[str, Any] = {}

        # Core fields
        if form_state.get("title"):
            updated_data["title"] = form_state["title"]
        if form_state.get("description"):
            updated_data["description"] = form_state["description"]
        if form_state.get("location"):
            updated_data["location"] = form_state["location"]

        # Date/time fields
        try:
            if form_state.get("event_date"):
                updated_data["event_date"] = date.fromisoformat(
                    form_state["event_date"]
                )
            if form_state.get("start_time"):
                updated_data["start_time"] = time.fromisoformat(
                    form_state["start_time"]
                )
            if form_state.get("end_time"):
                updated_data["end_time"] = time.fromisoformat(form_state["end_time"])
        except ValueError as e:
            logger.warning(f"Failed to parse date/time fields: {e}")

        # Button configuration
        button_config = form_state.get("button_config", {})
        if button_config.get("button_type"):
            updated_data["button_type"] = button_config["button_type"]
        if button_config.get("primary_button_text"):
            updated_data["primary_button_text"] = button_config["primary_button_text"]
        if "secondary_button_text" in button_config:
            updated_data["secondary_button_text"] = button_config[
                "secondary_button_text"
            ]

        # Update core form data
        if updated_data:
            result = self.signup_form_service.update_signup_form(form_id, updated_data)
            if not result.get("success"):
                raise Exception(
                    f"Failed to update form: {result.get('error', 'unknown error')}"
                )

        # Update custom fields (authoritative list - replaces existing)
        if "custom_fields" in form_state:
            custom_fields = form_state["custom_fields"]
            logger.info(
                f"Updating custom fields for form {form_id}, fields from state: {[f.get('field_name') for f in custom_fields]}"
            )

            custom_fields_data = [
                {
                    "field_name": field.get("field_name"),
                    "field_type": field.get("field_type"),
                    "label": field.get("label"),
                    "placeholder": field.get("placeholder"),
                    "is_required": field.get("is_required", False),
                    "options": field.get("options"),
                    "field_order": field.get("field_order", i),
                }
                for i, field in enumerate(custom_fields)
            ]

            # Upsert fields and remove any not in the list
            self.form_field_service.upsert_form_fields(form_id, custom_fields_data)
            keep_names = [cf.get("field_name") for cf in custom_fields_data]
            logger.info(f"Keeping fields: {keep_names}, deleting others")
            deleted_count = self.form_field_service.delete_fields_not_in(
                form_id, keep_names
            )
            logger.info(f"Deleted {deleted_count} fields")
            self.form_field_service.db.commit()
            logger.info(f"Committed custom field changes for form {form_id}")

        # Handle timeslot updates for drafts only
        timeslot_summary = []
        if existing_form.status == FormStatus.DRAFT and form_state.get(
            "timeslot_schedule"
        ):
            try:
                ts_service = TimeslotService(self.signup_form_service.db)
                schedule_dict = dict(form_state["timeslot_schedule"])

                # Convert start_from_date if present
                if schedule_dict.get("start_from_date"):
                    try:
                        schedule_dict["start_from_date"] = date.fromisoformat(
                            schedule_dict["start_from_date"]
                        )
                    except ValueError:
                        schedule_dict.pop("start_from_date", None)

                schedule = TimeslotSchedule(**schedule_dict)
                result = ts_service.add_schedule(form_id, schedule)
                timeslot_summary.append(
                    f"Timeslots: {result.added_count} added ({result.skipped_existing} existing)"
                )
            except Exception as e:
                logger.warning(f"Failed to update timeslots: {e}")

        # Generate preview URL
        preview_url = f"{config['app_base_url']}/form/{existing_form.url_slug}"

        # Build response
        response = (
            f"Perfect! I've updated your draft.\n\n"
            f"**{existing_form.title}**\n"
            f"Preview: {preview_url}\n\n"
        )

        if timeslot_summary:
            response += "\n".join(timeslot_summary) + "\n\n"

        response += "Continue making changes or say 'publish the form' when ready!"

        return response

    async def _generate_url_slug(self, title: str, event_date: str) -> str:
        """
        Generate a URL-friendly slug for the form.

        Args:
            title: Form title
            event_date: Event date string

        Returns:
            URL slug (e.g., "birthday-party-dec-15-a1b2c3d4")
        """
        try:
            # Ask LLM to generate slug
            prompt = f"""Generate a short, URL-friendly slug for an event form.

Event Details:
- Title: {title}
- Date: {event_date}

Requirements:
- Use lowercase letters, numbers, and hyphens only
- Maximum 30 characters
- Be descriptive but concise
- Remove special characters and spaces

Examples:
- "Birthday Party" on "2025-12-15" → "birthday-party-dec-15"
- "Python Workshop" on "2025-01-20" → "python-workshop-jan-20"

Generate only the slug, no explanation:"""

            response = await self.llm_client.process_instruction(
                messages=[{"role": "user", "content": prompt}], max_tokens=50
            )

            slug = response.strip().lower()
            # Clean the slug
            slug = re.sub(r"[^a-z0-9-]", "", slug)
            slug = re.sub(r"-+", "-", slug)  # Remove consecutive hyphens
            slug = slug.strip("-")  # Remove leading/trailing hyphens

            if len(slug) > 30:
                slug = slug[:30].rstrip("-")

            # Add unique suffix
            unique_suffix = uuid.uuid4().hex[:8]
            final_slug = f"{slug}-{unique_suffix}"

            return final_slug

        except Exception as e:
            logger.error(f"Failed to generate slug with LLM: {e}")
            # Fallback to simple slug
            simple_slug = re.sub(r"[^a-z0-9\s]", "", title.lower())
            simple_slug = re.sub(r"\s+", "-", simple_slug)
            simple_slug = simple_slug[:22].strip("-")
            unique_suffix = uuid.uuid4().hex[:8]
            return f"{simple_slug}-{unique_suffix}"
