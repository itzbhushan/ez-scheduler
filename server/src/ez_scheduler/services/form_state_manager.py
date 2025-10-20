import json
import logging
from typing import Any, Dict

import redis

logger = logging.getLogger(__name__)


class FormStateManager:
    """
    Manages form state in Redis with automatic TTL.

    Stores partial form state during conversation flows, enabling:
    - Incremental form building across multiple conversation turns
    - Automatic state expiration (30-minute sliding window)
    - State completeness validation
    - Smart merging of nested structures (custom_fields, button_config)
    """

    def __init__(self, redis_client: redis.Redis, ttl_seconds: int = 1800):
        """
        Initialize FormStateManager with Redis backend.

        Args:
            redis_client: Redis client instance (from dependency injection)
            ttl_seconds: Time-to-live in seconds (default: 1800 = 30 minutes)
        """
        self.redis_client = redis_client
        self.ttl_seconds = ttl_seconds

    def _state_key(self, thread_id: str) -> str:
        """
        Generate Redis key for form state.

        Args:
            thread_id: Conversation thread identifier

        Returns:
            Redis key (format: "form_state:{thread_id}")
        """
        return f"form_state:{thread_id}"

    def _empty_state_template(self) -> Dict[str, Any]:
        """
        Get empty form state template.

        Returns:
            Dictionary with all form fields set to None/empty values
        """
        return {
            "title": None,
            "event_date": None,
            "start_time": None,
            "end_time": None,
            "location": None,
            "description": None,
            "custom_fields": [],
            "button_config": None,
            "timeslot_schedule": None,
            "is_complete": False,
            "form_id": None,
        }

    def get_state(self, thread_id: str) -> Dict[str, Any]:
        """
        Retrieve form state for a conversation thread.

        Args:
            thread_id: Conversation thread identifier

        Returns:
            Form state dictionary (empty template if not found or corrupted)

        Raises:
            redis.RedisError: If Redis operation fails
        """
        key = self._state_key(thread_id)
        try:
            state_json = self.redis_client.get(key)

            if not state_json:
                return self._empty_state_template()

            try:
                return json.loads(state_json)
            except json.JSONDecodeError:
                logger.error(f"Corrupted state for thread {thread_id}, returning empty")
                return self._empty_state_template()

        except redis.RedisError as e:
            logger.error(f"Redis error getting state for thread {thread_id}: {e}")
            raise

    def _merge_custom_fields(self, current: list, updates: list) -> list:
        """
        Replace custom fields with the new list from LLM.

        This allows the LLM to add, modify, or remove fields by simply
        returning the complete desired list of custom fields.

        Args:
            current: Current custom fields list (ignored)
            updates: New custom fields to use

        Returns:
            The updates list as-is (complete replacement)
        """
        # Complete replacement - LLM returns the full desired list
        return updates

    def _merge_state(
        self, current: Dict[str, Any], updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Merge state updates with current state.

        Handles special merging logic for:
        - custom_fields: Merged by field_name
        - button_config: Deep merged
        - Other fields: Simple overwrite

        Args:
            current: Current form state
            updates: Updates to apply

        Returns:
            Merged state dictionary
        """
        merged = current.copy()

        for key, value in updates.items():
            if key == "custom_fields" and isinstance(value, list):
                # Merge custom fields by field_name
                merged[key] = self._merge_custom_fields(
                    merged.get("custom_fields", []), value
                )
            elif key == "button_config" and isinstance(value, dict):
                # Merge button config (deep merge)
                current_config = merged.get("button_config", {})
                if current_config is None:
                    current_config = {}
                merged[key] = {**current_config, **value}
            else:
                # Simple overwrite for other fields
                merged[key] = value

        return merged

    def update_state(self, thread_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update form state with new data and refresh TTL.

        Args:
            thread_id: Conversation thread identifier
            updates: Dictionary of fields to update

        Returns:
            Complete updated form state

        Raises:
            redis.RedisError: If Redis operation fails
        """
        try:
            # Get current state
            current_state = self.get_state(thread_id)

            # Merge updates
            merged_state = self._merge_state(current_state, updates)

            # Update completeness flag
            merged_state["is_complete"] = self.is_complete(merged_state)

            # Save with TTL (sliding window)
            key = self._state_key(thread_id)
            self.redis_client.setex(key, self.ttl_seconds, json.dumps(merged_state))

            return merged_state

        except redis.RedisError as e:
            logger.error(f"Redis error updating state for thread {thread_id}: {e}")
            raise

    def is_complete(self, state: Dict[str, Any]) -> bool:
        """
        Check if form state has all required fields.

        Required fields:
        - title (non-empty string)
        - event_date (non-empty string)
        - location (non-empty string)
        - description (non-empty string)
        - button_config.button_type (non-empty string)
        - button_config.primary_button_text (non-empty string)

        Args:
            state: Form state dictionary to validate

        Returns:
            True if all required fields are present and non-empty
        """
        required_fields = ["title", "event_date", "location", "description"]

        # Check basic required fields
        for field in required_fields:
            value = state.get(field)
            if not value or (isinstance(value, str) and not value.strip()):
                return False

        # Check button_config
        button_config = state.get("button_config", {})
        if button_config is None:
            return False

        if not button_config.get("button_type") or not button_config.get(
            "primary_button_text"
        ):
            return False

        return True

    def clear_state(self, thread_id: str) -> None:
        """
        Clear form state for a conversation thread.

        Args:
            thread_id: Conversation thread identifier

        Raises:
            redis.RedisError: If Redis operation fails
        """
        key = self._state_key(thread_id)
        try:
            self.redis_client.delete(key)
            logger.info(f"Cleared form state for thread {thread_id}")
        except redis.RedisError as e:
            logger.error(f"Redis error clearing state for thread {thread_id}: {e}")
            raise
