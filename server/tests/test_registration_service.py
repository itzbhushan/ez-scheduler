"""Tests for registration service functionality"""

import uuid
from datetime import date, time

import pytest
from ez_scheduler.models.signup_form import SignupForm


class TestRegistrationService:
    """Test registration service functionality"""

    def _create_test_form(
        self, user_service, signup_service, title="Test Event", is_active=True
    ):
        """Helper method to create a test signup form"""
        user = user_service.create_user(
            email=f"test-{uuid.uuid4()}@example.com", name="Test User"
        )

        form = SignupForm(
            id=uuid.uuid4(),
            user_id=user.id,
            title=title,
            event_date=date(2024, 12, 25),
            start_time=time(14, 0),
            end_time=time(16, 0),
            location="Test Location",
            description="A test event for testing purposes",
            url_slug=f"test-event-{uuid.uuid4()}",
            is_active=is_active,
        )

        result = signup_service.create_signup_form(form)
        if result["success"]:
            # The form object was created and committed to database, return it
            # The form object should have been refreshed by the service
            return form
        else:
            raise Exception(
                f"Failed to create signup form: {result.get('error', 'Unknown error')}"
            )

    def test_create_registration_success(
        self, user_service, registration_service, signup_service
    ):
        """Test successful registration creation"""
        form = self._create_test_form(user_service, signup_service)

        registration = registration_service.create_registration(
            form_id=form.id, name="John Doe", email="john@example.com", phone="555-1234"
        )

        assert registration.id is not None
        assert registration.form_id == form.id
        assert registration.name == "John Doe"
        assert registration.email == "john@example.com"
        assert registration.phone == "555-1234"
        assert registration.registered_at is not None

    def test_create_registration_allows_duplicates(
        self, user_service, registration_service, signup_service
    ):
        """Test that duplicate registrations are now allowed (no unique constraint)"""
        form = self._create_test_form(user_service, signup_service)

        # Create first registration
        reg1 = registration_service.create_registration(
            form_id=form.id, name="John Doe", email="john@example.com", phone="555-1234"
        )

        # Create duplicate registration - should succeed now
        reg2 = registration_service.create_registration(
            form_id=form.id,
            name="Jane Doe",  # Different name, same email/phone/form
            email="john@example.com",
            phone="555-1234",
        )

        # Both registrations should exist
        assert reg1.id != reg2.id
        assert reg1.email == reg2.email
        assert reg1.phone == reg2.phone
        assert reg1.form_id == reg2.form_id

    def test_create_registration_same_user_different_forms(
        self, user_service, registration_service, signup_service
    ):
        """Test that same user can register for different forms"""
        form1 = self._create_test_form(user_service, signup_service, title="Event 1")
        form2 = self._create_test_form(user_service, signup_service, title="Event 2")

        # Register for first form
        reg1 = registration_service.create_registration(
            form_id=form1.id,
            name="John Doe",
            email="john@example.com",
            phone="555-1234",
        )

        # Register for second form - should succeed
        reg2 = registration_service.create_registration(
            form_id=form2.id,
            name="John Doe",
            email="john@example.com",
            phone="555-1234",
        )

        assert reg1.form_id != reg2.form_id
        assert reg1.email == reg2.email
        assert reg1.phone == reg2.phone

    def test_create_registration_inactive_form_fails(
        self, user_service, registration_service, signup_service
    ):
        """Test that registration fails for inactive form"""
        form = self._create_test_form(user_service, signup_service, is_active=False)

        with pytest.raises(ValueError, match="Form not found or inactive"):
            registration_service.create_registration(
                form_id=form.id,
                name="John Doe",
                email="john@example.com",
                phone="555-1234",
            )

    def test_create_registration_nonexistent_form_fails(self, registration_service):
        """Test that registration fails for non-existent form"""
        fake_form_id = str(uuid.uuid4())

        with pytest.raises(ValueError, match="Form not found or inactive"):
            registration_service.create_registration(
                form_id=fake_form_id,
                name="John Doe",
                email="john@example.com",
                phone="555-1234",
            )

    def test_get_registrations_for_form(
        self, user_service, registration_service, signup_service
    ):
        """Test getting all registrations for a form"""
        form = self._create_test_form(user_service, signup_service)

        # Create multiple registrations
        reg1 = registration_service.create_registration(
            form_id=form.id, name="John Doe", email="john@example.com", phone="555-1234"
        )

        reg2 = registration_service.create_registration(
            form_id=form.id,
            name="Jane Smith",
            email="jane@example.com",
            phone="555-5678",
        )

        registrations = registration_service.get_registrations_for_form(form.id)

        assert len(registrations) == 2
        registration_ids = [r.id for r in registrations]
        assert reg1.id in registration_ids
        assert reg2.id in registration_ids

    def test_get_registration_count_for_form(
        self, user_service, registration_service, signup_service
    ):
        """Test getting registration count for a form"""
        form = self._create_test_form(user_service, signup_service)

        # Initially no registrations
        assert registration_service.get_registration_count_for_form(form.id) == 0

        # Create registrations
        registration_service.create_registration(
            form_id=form.id, name="John Doe", email="john@example.com", phone="555-1234"
        )

        registration_service.create_registration(
            form_id=form.id,
            name="Jane Smith",
            email="jane@example.com",
            phone="555-5678",
        )

        assert registration_service.get_registration_count_for_form(form.id) == 2

    def test_get_registration_by_id(
        self, user_service, registration_service, signup_service
    ):
        """Test getting registration by ID"""
        form = self._create_test_form(user_service, signup_service)

        registration = registration_service.create_registration(
            form_id=form.id, name="John Doe", email="john@example.com", phone="555-1234"
        )

        found_registration = registration_service.get_registration_by_id(
            registration.id
        )

        assert found_registration is not None
        assert found_registration.id == registration.id
        assert found_registration.name == "John Doe"

        # Test non-existent ID
        fake_id = str(uuid.uuid4())
        not_found = registration_service.get_registration_by_id(fake_id)
        assert not_found is None
