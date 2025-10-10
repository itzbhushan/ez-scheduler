import json

import pytest

from ez_scheduler.services.form_state_manager import FormStateManager


@pytest.fixture
def form_state_manager(redis_client):
    """Create FormStateManager instance for testing."""
    return FormStateManager(redis_client=redis_client, ttl_seconds=1800)


def test_get_state_new_thread(form_state_manager, clean_redis):
    """Test getting state for new thread returns empty template."""
    thread_id = "test_thread_123"
    state = form_state_manager.get_state(thread_id)

    # Verify empty template structure
    assert state["title"] is None
    assert state["event_date"] is None
    assert state["location"] is None
    assert state["description"] is None
    assert state["custom_fields"] == []
    assert state["button_config"] is None
    assert state["is_complete"] is False
    assert state["form_id"] is None


def test_get_state_existing(form_state_manager, clean_redis):
    """Test getting existing state."""
    thread_id = "test_thread_456"
    test_state = {
        "title": "Test Event",
        "event_date": "2024-12-15",
        "location": "Test Location",
        "description": "Test description",
        "custom_fields": [],
        "button_config": {"button_type": "rsvp_yes_no"},
        "is_complete": False,
        "form_id": None,
    }

    # Save state directly to Redis
    key = f"form_state:{thread_id}"
    form_state_manager.redis_client.setex(key, 1800, json.dumps(test_state))

    # Retrieve and verify
    retrieved = form_state_manager.get_state(thread_id)
    assert retrieved["title"] == "Test Event"
    assert retrieved["event_date"] == "2024-12-15"
    assert retrieved["location"] == "Test Location"


def test_update_state_simple_fields(form_state_manager, clean_redis):
    """Test updating simple fields."""
    thread_id = "test_thread_789"

    # Update title and location
    updates = {"title": "Birthday Party", "location": "Central Park"}

    result = form_state_manager.update_state(thread_id, updates)

    assert result["title"] == "Birthday Party"
    assert result["location"] == "Central Park"
    assert result["event_date"] is None  # Unchanged


def test_update_state_custom_fields_merge(form_state_manager, clean_redis):
    """Test merging custom fields by field_name."""
    thread_id = "test_thread_custom"

    # Add first custom field
    updates1 = {
        "custom_fields": [
            {
                "field_name": "guest_count",
                "field_type": "number",
                "label": "Number of guests",
                "is_required": True,
            }
        ]
    }
    form_state_manager.update_state(thread_id, updates1)

    # Add second custom field
    updates2 = {
        "custom_fields": [
            {
                "field_name": "dietary_restrictions",
                "field_type": "text",
                "label": "Dietary Restrictions",
                "is_required": False,
            }
        ]
    }
    result = form_state_manager.update_state(thread_id, updates2)

    # Should have both fields
    assert len(result["custom_fields"]) == 2
    field_names = {f["field_name"] for f in result["custom_fields"]}
    assert "guest_count" in field_names
    assert "dietary_restrictions" in field_names


def test_update_state_custom_fields_overwrite(form_state_manager, clean_redis):
    """Test updating existing custom field."""
    thread_id = "test_thread_overwrite"

    # Add custom field
    updates1 = {
        "custom_fields": [
            {
                "field_name": "guest_count",
                "field_type": "number",
                "label": "Number of guests",
                "is_required": True,
            }
        ]
    }
    form_state_manager.update_state(thread_id, updates1)

    # Update same field with different properties
    updates2 = {
        "custom_fields": [
            {
                "field_name": "guest_count",
                "field_type": "number",
                "label": "How many guests?",
                "is_required": False,
            }
        ]
    }
    result = form_state_manager.update_state(thread_id, updates2)

    # Should have only one field with updated properties
    assert len(result["custom_fields"]) == 1
    field = result["custom_fields"][0]
    assert field["label"] == "How many guests?"
    assert field["is_required"] is False


def test_update_state_button_config_merge(form_state_manager, clean_redis):
    """Test merging button config."""
    thread_id = "test_thread_button"

    # Set button type
    updates1 = {"button_config": {"button_type": "rsvp_yes_no"}}
    form_state_manager.update_state(thread_id, updates1)

    # Add button text
    updates2 = {
        "button_config": {
            "primary_button_text": "RSVP Yes",
            "secondary_button_text": "RSVP No",
        }
    }
    result = form_state_manager.update_state(thread_id, updates2)

    # Should have all button config fields
    assert result["button_config"]["button_type"] == "rsvp_yes_no"
    assert result["button_config"]["primary_button_text"] == "RSVP Yes"
    assert result["button_config"]["secondary_button_text"] == "RSVP No"


def test_is_complete_field_storage(form_state_manager, clean_redis):
    """Test that is_complete field is stored and retrieved correctly."""
    thread_id = "test_thread_complete"

    # Set is_complete to False explicitly
    updates1 = {
        "title": "Test",
        "is_complete": False,
    }
    result1 = form_state_manager.update_state(thread_id, updates1)
    assert result1["is_complete"] is False

    # Set is_complete to True explicitly
    updates2 = {
        "is_complete": True,
    }
    result2 = form_state_manager.update_state(thread_id, updates2)
    assert result2["is_complete"] is True

    # Verify it persists
    state = form_state_manager.get_state(thread_id)
    assert state["is_complete"] is True


def test_is_complete_defaults_to_false(form_state_manager, clean_redis):
    """Test that is_complete defaults to False for new state."""
    thread_id = "test_thread_default"

    # Get new state - should default to False
    state = form_state_manager.get_state(thread_id)
    assert state["is_complete"] is False

    # Update without setting is_complete - should remain False
    updates = {
        "title": "Test Event",
        "event_date": "2024-12-15",
        "location": "Test Location",
        "description": "Test description",
        "button_config": {
            "button_type": "rsvp_yes_no",
            "primary_button_text": "RSVP Yes",
        },
    }
    result = form_state_manager.update_state(thread_id, updates)
    assert result["is_complete"] is False


def test_clear_state(form_state_manager, clean_redis):
    """Test clearing form state."""
    thread_id = "test_thread_clear"

    # Create state
    updates = {"title": "Test Event", "location": "Test Location"}
    form_state_manager.update_state(thread_id, updates)

    # Verify state exists
    state = form_state_manager.get_state(thread_id)
    assert state["title"] == "Test Event"

    # Clear state
    form_state_manager.clear_state(thread_id)

    # Verify state is cleared (returns empty template)
    state = form_state_manager.get_state(thread_id)
    assert state["title"] is None


def test_ttl_sliding_window(form_state_manager, clean_redis):
    """Test that TTL is refreshed on updates."""
    thread_id = "test_thread_ttl"

    # Initial update
    form_state_manager.update_state(thread_id, {"title": "Test"})

    # Check TTL
    key = f"form_state:{thread_id}"
    ttl_1 = form_state_manager.redis_client.ttl(key)
    assert ttl_1 > 0

    # Update again
    form_state_manager.update_state(thread_id, {"location": "Location"})

    # TTL should be reset
    ttl_2 = form_state_manager.redis_client.ttl(key)
    assert ttl_2 > ttl_1 - 5  # Allow small timing differences


def test_state_persistence(form_state_manager, clean_redis):
    """Test that state persists across multiple updates."""
    thread_id = "test_thread_persist"

    # Multiple updates
    form_state_manager.update_state(thread_id, {"title": "Test Event"})
    form_state_manager.update_state(thread_id, {"event_date": "2024-12-15"})
    form_state_manager.update_state(thread_id, {"location": "Test Location"})

    # All updates should be present
    state = form_state_manager.get_state(thread_id)
    assert state["title"] == "Test Event"
    assert state["event_date"] == "2024-12-15"
    assert state["location"] == "Test Location"


def test_form_id_tracking(form_state_manager, clean_redis):
    """Test tracking form_id for draft updates."""
    thread_id = "test_thread_formid"

    # Initially no form_id
    state = form_state_manager.get_state(thread_id)
    assert state["form_id"] is None

    # Set form_id after draft creation
    form_state_manager.update_state(thread_id, {"form_id": "uuid-123-456"})

    # Verify form_id is tracked
    state = form_state_manager.get_state(thread_id)
    assert state["form_id"] == "uuid-123-456"


def test_is_complete_explicit_control(form_state_manager, clean_redis):
    """Test that is_complete is controlled by explicit updates (LLM decides)."""
    thread_id = "test_thread_explicit"

    # Initially False
    form_state_manager.update_state(thread_id, {"title": "Test"})
    state = form_state_manager.get_state(thread_id)
    assert state["is_complete"] is False

    # Even with all fields, is_complete remains False unless explicitly set
    complete_updates = {
        "title": "Test Event",
        "event_date": "2024-12-15",
        "location": "Test Location",
        "description": "Test description",
        "button_config": {
            "button_type": "rsvp_yes_no",
            "primary_button_text": "Yes",
        },
    }
    form_state_manager.update_state(thread_id, complete_updates)
    state = form_state_manager.get_state(thread_id)
    assert state["is_complete"] is False

    # Only becomes True when explicitly set (by LLM)
    form_state_manager.update_state(thread_id, {"is_complete": True})
    state = form_state_manager.get_state(thread_id)
    assert state["is_complete"] is True


def test_corrupted_state_recovery(form_state_manager, clean_redis):
    """Test recovery from corrupted state in Redis."""
    thread_id = "test_thread_corrupt"

    # Save corrupted JSON to Redis
    key = f"form_state:{thread_id}"
    form_state_manager.redis_client.setex(key, 1800, "invalid json {{{")

    # Should return empty template instead of crashing
    state = form_state_manager.get_state(thread_id)
    assert state["title"] is None
    assert state["is_complete"] is False
