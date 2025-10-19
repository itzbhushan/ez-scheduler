import logging
import uuid
from typing import Dict, List, Literal

import redis
from langchain_community.chat_message_histories import RedisChatMessageHistory

logger = logging.getLogger(__name__)


class ConversationManager:
    """
    Manages conversation threads and message history using LangChain's RedisChatMessageHistory.

    Provides transparent conversation context management:
    - Auto-detects active threads for users (no thread_id tracking needed by clients)
    - Stores messages with automatic TTL (30-minute sliding window)
    - Handles message history trimming
    - Distributed-ready (works across multiple servers)
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        redis_url: str,
        ttl_seconds: int = 1800,  # 30 minutes
        max_messages_per_thread: int = 20,
    ):
        """
        Initialize ConversationManager with Redis backend.

        Args:
            redis_client: Redis client instance (from dependency injection)
            redis_url: Redis connection URL for LangChain (e.g., "redis://localhost:6379/0")
            ttl_seconds: Time-to-live in seconds (default: 1800 = 30 minutes)
            max_messages_per_thread: Maximum messages to retain per thread (default: 20)
        """
        self.redis_client = redis_client
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds
        self.max_messages_per_thread = max_messages_per_thread

    def _get_history(self, thread_id: str) -> RedisChatMessageHistory:
        """
        Get LangChain's RedisChatMessageHistory instance for a thread.

        Args:
            thread_id: Conversation thread identifier

        Returns:
            RedisChatMessageHistory instance with automatic TTL
        """
        return RedisChatMessageHistory(
            session_id=thread_id,
            url=self.redis_url,
            ttl=self.ttl_seconds,  # LangChain handles TTL automatically
        )

    def get_or_create_thread_for_user(self, user_id: str) -> str:
        """
        Auto-detect or create conversation thread for a user.

        This is the key method that makes thread management transparent to clients.
        Returns the user's active thread if one exists (within TTL window),
        otherwise creates a new thread.

        Args:
            user_id: User identifier

        Returns:
            Thread ID (format: "{user_id}::conv::{random_id}")

        Raises:
            redis.RedisError: If Redis operation fails
        """
        # Step 1: Check for active thread
        key = f"active_thread:{user_id}"
        try:
            active_thread = self.redis_client.get(key)
        except redis.RedisError as e:
            logger.error(f"Redis error getting active thread for user {user_id}: {e}")
            raise

        # Step 2: If found, verify it still has messages
        if active_thread:
            try:
                history = self._get_history(active_thread)
                if history.messages:
                    logger.info(
                        f"Resuming active thread for user {user_id}: {active_thread}"
                    )
                    return active_thread
            except redis.RedisError as e:
                logger.warning(
                    f"Redis error verifying thread {active_thread}, creating new: {e}"
                )
                # Fall through to create new thread

        # Step 3: No active thread, create new one
        new_thread_id = f"{user_id}::conv::{uuid.uuid4().hex[:12]}"
        try:
            self.redis_client.setex(key, self.ttl_seconds, new_thread_id)
        except redis.RedisError as e:
            logger.error(f"Redis error creating thread for user {user_id}: {e}")
            raise

        logger.info(f"Created new thread for user {user_id}: {new_thread_id}")
        return new_thread_id

    def add_message(
        self, thread_id: str, role: Literal["user", "assistant"], content: str
    ) -> None:
        """
        Add a message to conversation history with automatic TTL refresh.

        Args:
            thread_id: Conversation thread identifier
            role: Message role ("user" or "assistant")
            content: Message content

        Raises:
            ValueError: If role is invalid or content is empty
            redis.RedisError: If Redis operation fails
        """
        if not content or not content.strip():
            raise ValueError("Message content cannot be empty")

        if role not in ["user", "assistant"]:
            raise ValueError(f"Invalid role: {role}. Must be 'user' or 'assistant'")

        try:
            history = self._get_history(thread_id)

            # Add message (LangChain handles serialization)
            if role == "user":
                history.add_user_message(content)
            else:
                history.add_ai_message(content)

            # Trim to max messages if needed
            messages = history.messages
            if len(messages) > self.max_messages_per_thread:
                # Keep only the most recent messages
                trimmed_messages = messages[-self.max_messages_per_thread :]
                history.clear()
                for msg in trimmed_messages:
                    if msg.type == "human":
                        history.add_user_message(msg.content)
                    else:
                        history.add_ai_message(msg.content)
                logger.info(
                    f"Trimmed thread {thread_id} to {self.max_messages_per_thread} messages"
                )

            # Update active thread tracker with sliding window TTL
            user_id = thread_id.split("::")[0]
            self.redis_client.setex(
                f"active_thread:{user_id}", self.ttl_seconds, thread_id
            )
        except redis.RedisError as e:
            logger.error(f"Redis error adding message to thread {thread_id}: {e}")
            raise

    def get_history(self, thread_id: str) -> List[Dict[str, str]]:
        """
        Retrieve conversation history for a thread.

        Args:
            thread_id: Conversation thread identifier

        Returns:
            List of message dictionaries with 'role' and 'content' keys
            Example: [
                {"role": "user", "content": "Create a form..."},
                {"role": "assistant", "content": "I'd love to help!"}
            ]

        Raises:
            redis.RedisError: If Redis operation fails
        """
        try:
            history = self._get_history(thread_id)
            messages = history.messages

            # Convert LangChain format to simple dict
            return [
                {
                    "role": "user" if msg.type == "human" else "assistant",
                    "content": msg.content,
                }
                for msg in messages
            ]
        except redis.RedisError as e:
            logger.error(f"Redis error getting history for thread {thread_id}: {e}")
            raise

    def clear_history(self, thread_id: str) -> None:
        """
        Clear conversation history and active thread tracking.

        Args:
            thread_id: Conversation thread identifier

        Raises:
            redis.RedisError: If Redis operation fails
        """
        try:
            # Clear message history
            history = self._get_history(thread_id)
            history.clear()

            # Clear active thread tracker if this was the active one
            user_id = thread_id.split("::")[0]
            key = f"active_thread:{user_id}"
            current_active = self.redis_client.get(key)
            if current_active and current_active == thread_id:
                self.redis_client.delete(key)
                logger.info(f"Cleared active thread for user {user_id}")
        except redis.RedisError as e:
            logger.error(f"Redis error clearing history for thread {thread_id}: {e}")
            raise
