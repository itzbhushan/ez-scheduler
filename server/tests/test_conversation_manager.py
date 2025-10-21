import time

import pytest

from ez_scheduler.services.conversation_manager import ConversationManager


@pytest.fixture
def conversation_manager(redis_client, redis_url):
    """Create ConversationManager instance for testing."""
    return ConversationManager(
        redis_client=redis_client,
        redis_url=redis_url,
        ttl_seconds=1800,
        max_messages_per_thread=20,
    )


@pytest.fixture
def clean_redis(conversation_manager):
    """Clean up Redis after each test."""
    yield
    # Clean up all test keys
    conversation_manager.redis_client.flushdb()


def test_get_or_create_thread_new_user(conversation_manager, clean_redis):
    """Test thread creation for new user."""
    user_id = "test_user_123"
    thread_id = conversation_manager.get_or_create_thread_for_user(user_id)

    # Verify thread ID format
    assert thread_id.startswith(f"{user_id}::conv::")
    assert len(thread_id.split("::")) == 3

    # Verify active thread is tracked
    active_thread = conversation_manager.redis_client.get(f"active_thread:{user_id}")
    assert active_thread == thread_id


def test_get_or_create_thread_existing_active(conversation_manager, clean_redis):
    """Test returning existing active thread."""
    user_id = "test_user_456"

    # Create first thread and add a message
    thread_id_1 = conversation_manager.get_or_create_thread_for_user(user_id)
    conversation_manager.add_message(thread_id_1, "user", "Hello")

    # Get thread again - should return same thread
    thread_id_2 = conversation_manager.get_or_create_thread_for_user(user_id)
    assert thread_id_1 == thread_id_2


def test_get_or_create_thread_expired(conversation_manager, clean_redis):
    """Test creating new thread when previous one expired."""
    user_id = "test_user_789"

    # Create thread with very short TTL
    short_ttl_manager = ConversationManager(
        redis_client=conversation_manager.redis_client,
        redis_url=conversation_manager.redis_url,
        ttl_seconds=1,  # 1 second TTL
        max_messages_per_thread=20,
    )

    # Create first thread
    thread_id_1 = short_ttl_manager.get_or_create_thread_for_user(user_id)
    short_ttl_manager.add_message(thread_id_1, "user", "Hello")

    # Wait for expiration
    time.sleep(2)

    # Should create new thread
    thread_id_2 = short_ttl_manager.get_or_create_thread_for_user(user_id)
    assert thread_id_1 != thread_id_2


def test_add_message_user(conversation_manager, clean_redis):
    """Test adding user message."""
    user_id = "test_user_msg_1"
    thread_id = conversation_manager.get_or_create_thread_for_user(user_id)

    conversation_manager.add_message(thread_id, "user", "Hello, world!")

    history = conversation_manager.get_history(thread_id)
    assert len(history) == 1
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Hello, world!"


def test_add_message_assistant(conversation_manager, clean_redis):
    """Test adding assistant message."""
    user_id = "test_user_msg_2"
    thread_id = conversation_manager.get_or_create_thread_for_user(user_id)

    conversation_manager.add_message(thread_id, "assistant", "How can I help?")

    history = conversation_manager.get_history(thread_id)
    assert len(history) == 1
    assert history[0]["role"] == "assistant"
    assert history[0]["content"] == "How can I help?"


def test_add_message_trimming(conversation_manager, clean_redis):
    """Test message history trimming when exceeding max_messages."""
    user_id = "test_user_trim"
    thread_id = conversation_manager.get_or_create_thread_for_user(user_id)

    # Create manager with small max_messages
    small_manager = ConversationManager(
        redis_client=conversation_manager.redis_client,
        redis_url=conversation_manager.redis_url,
        ttl_seconds=1800,
        max_messages_per_thread=5,
    )

    # Add 10 messages
    for i in range(10):
        role = "user" if i % 2 == 0 else "assistant"
        small_manager.add_message(thread_id, role, f"Message {i}")

    # Should only keep last 5 messages
    history = small_manager.get_history(thread_id)
    assert len(history) == 5
    assert history[0]["content"] == "Message 5"
    assert history[-1]["content"] == "Message 9"


def test_get_history(conversation_manager, clean_redis):
    """Test retrieving conversation history."""
    user_id = "test_user_history"
    thread_id = conversation_manager.get_or_create_thread_for_user(user_id)

    # Add multiple messages
    conversation_manager.add_message(thread_id, "user", "Create a form")
    conversation_manager.add_message(thread_id, "assistant", "Sure! What's it for?")
    conversation_manager.add_message(thread_id, "user", "A birthday party")

    history = conversation_manager.get_history(thread_id)
    assert len(history) == 3
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
    assert history[2]["role"] == "user"


def test_get_history_empty_thread(conversation_manager, clean_redis):
    """Test getting history for thread with no messages."""
    user_id = "test_user_empty"
    thread_id = conversation_manager.get_or_create_thread_for_user(user_id)

    history = conversation_manager.get_history(thread_id)
    assert len(history) == 0


def test_clear_history(conversation_manager, clean_redis):
    """Test clearing conversation history."""
    user_id = "test_user_clear"
    thread_id = conversation_manager.get_or_create_thread_for_user(user_id)

    # Add messages
    conversation_manager.add_message(thread_id, "user", "Hello")
    conversation_manager.add_message(thread_id, "assistant", "Hi there!")

    # Clear history
    conversation_manager.clear_history(thread_id)

    # Verify history is empty
    history = conversation_manager.get_history(thread_id)
    assert len(history) == 0

    # Verify active thread is cleared
    active_thread = conversation_manager.redis_client.get(f"active_thread:{user_id}")
    assert active_thread is None


def test_active_thread_updates_on_add_message(conversation_manager, clean_redis):
    """Test that active thread TTL is refreshed on each message."""
    user_id = "test_user_ttl"
    thread_id = conversation_manager.get_or_create_thread_for_user(user_id)

    # Wait a bit before adding first message
    time.sleep(2)

    # Add message
    conversation_manager.add_message(thread_id, "user", "Message 1")

    # Check TTL
    ttl_1 = conversation_manager.redis_client.ttl(f"active_thread:{user_id}")

    # Wait a bit
    time.sleep(2)

    # Add another message
    conversation_manager.add_message(thread_id, "assistant", "Response 1")

    # Check TTL again - should be reset
    ttl_2 = conversation_manager.redis_client.ttl(f"active_thread:{user_id}")

    # TTL should be reset (close to original TTL)
    # Allow for small differences due to timing
    assert ttl_2 >= ttl_1 - 1


def test_invalid_role(conversation_manager, clean_redis):
    """Test adding message with invalid role."""
    user_id = "test_user_invalid"
    thread_id = conversation_manager.get_or_create_thread_for_user(user_id)

    with pytest.raises(ValueError, match="Invalid role"):
        conversation_manager.add_message(thread_id, "admin", "Invalid message")


def test_empty_content(conversation_manager, clean_redis):
    """Test adding message with empty content."""
    user_id = "test_user_empty_content"
    thread_id = conversation_manager.get_or_create_thread_for_user(user_id)

    with pytest.raises(ValueError, match="Message content cannot be empty"):
        conversation_manager.add_message(thread_id, "user", "")

    with pytest.raises(ValueError, match="Message content cannot be empty"):
        conversation_manager.add_message(thread_id, "user", "   ")
