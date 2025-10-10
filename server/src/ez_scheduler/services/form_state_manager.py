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
        Merge custom fields lists, updating by field_name.

        Args:
            current: Current custom fields list
            updates: New custom fields to merge

        Returns:
            Merged custom fields list
        """
        # Create dict for O(1) lookup
        merged_dict = {field["field_name"]: field for field in current}

        # Update with new fields
        for field in updates:
            field_name = field.get("field_name")
            if field_name:
                merged_dict[field_name] = field

        return list(merged_dict.values())

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

            # Note: is_complete is NOT calculated here - it's determined by the LLM
            # and passed through as part of the updates

            # Save with TTL (sliding window)
            key = self._state_key(thread_id)
            self.redis_client.setex(key, self.ttl_seconds, json.dumps(merged_state))

            return merged_state

        except redis.RedisError as e:
            logger.error(f"Redis error updating state for thread {thread_id}: {e}")
            raise

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
