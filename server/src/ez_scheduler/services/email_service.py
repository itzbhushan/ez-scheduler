"""Email service for generating and sending customized emails"""

import json
import logging
from typing import Dict

from ez_scheduler.backends.email_client import EmailClient
from ez_scheduler.backends.llm_client import LLMClient
from ez_scheduler.models.registration import Registration
from ez_scheduler.models.signup_form import SignupForm
from ez_scheduler.system_prompts import EMAIL_GENERATION_PROMPT

logger = logging.getLogger(__name__)


class EmailService:
    """Service for generating and sending customized emails based on registration context"""

    def __init__(self, llm_client: LLMClient, email_config: dict):
        self.llm_client = llm_client
        self.email_client = EmailClient(email_config)

    async def send_registration_email(
        self,
        form: SignupForm,
        registration: Registration,
        form_url: str,
    ) -> bool:
        """
        Generate and send personalized email using LLM based on form type and RSVP response.

        Args:
            form: The signup form
            registration: The registration data
            form_url: Full URL to the signup form

        Returns:
            bool: True if email was sent successfully, False otherwise
        """
        if not registration.email:
            logger.info("No email provided, skipping email confirmation")
            return False

        try:
            # Extract RSVP response from registration data
            rsvp_response = None
            if registration.additional_data:
                rsvp_response = registration.additional_data.get("rsvp_response")

            # Determine email type based on form and RSVP response
            if form.button_type == "rsvp_yes_no":
                if rsvp_response == "yes":
                    email_type = "rsvp_yes"
                elif rsvp_response == "no":
                    email_type = "rsvp_no"
                else:
                    email_type = "rsvp_yes"  # Default to yes if unclear
            else:
                email_type = "registration"  # Single submit forms

            # Format event details
            event_details = self._format_event_details(form)

            # Create LLM prompt with all context
            user_message = f"""Generate an email for this {email_type} scenario:

EMAIL TYPE: {email_type}
REGISTRANT: {registration.name}
EVENT DETAILS:
{event_details}

FORM URL: {form_url}

Generate appropriate email subject and body for this scenario."""

            messages = [{"role": "user", "content": user_message}]

            response = await self.llm_client.process_instruction(
                messages=messages, system=EMAIL_GENERATION_PROMPT, max_tokens=300
            )

            # Parse the LLM response as JSON
            email_content = self._parse_json_response(response)

            logger.info(f"Generated {email_type} email for {registration.name}")

            # Send the email
            return await self._send_email(registration.email, email_content)

        except Exception as e:
            logger.warning(f"Failed to generate LLM email content: {e}")
            # Fallback to simple email
            email_content = self._generate_fallback_email(form, registration)
            return await self._send_email(registration.email, email_content)

    def _format_event_details(self, form: SignupForm) -> str:
        """Format event details for LLM prompt"""
        details = []
        details.append(f"Title: {form.title}")
        details.append(f"Date: {form.event_date.strftime('%B %d, %Y')}")

        if form.start_time:
            time_str = form.start_time.strftime("%I:%M %p")
            if form.end_time:
                time_str += f" - {form.end_time.strftime('%I:%M %p')}"
            details.append(f"Time: {time_str}")

        details.append(f"Location: {form.location}")

        if form.description:
            details.append(f"Description: {form.description}")

        return "\n".join(details)

    def _parse_json_response(self, response: str) -> Dict[str, str]:
        """Parse LLM JSON response to extract subject and body"""
        try:
            # Try to parse as JSON
            email_data = json.loads(response.strip())

            # Validate required keys
            if "subject" not in email_data or "body" not in email_data:
                raise ValueError("Missing required keys in JSON response")

            return {
                "subject": str(email_data["subject"]).strip(),
                "body": str(email_data["body"]).strip(),
            }

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse LLM JSON response: {e}")
            # Fallback parsing for malformed responses
            lines = response.strip().split("\n")
            if len(lines) >= 2:
                return {
                    "subject": lines[0].strip(),
                    "body": "\n".join(lines[1:]).strip(),
                }
            return {
                "subject": "Registration Confirmation",
                "body": "Thank you for your registration!",
            }

    def _generate_fallback_email(
        self, form: SignupForm, registration: Registration
    ) -> Dict[str, str]:
        """Generate a simple fallback email if LLM fails"""

        # Extract RSVP response from registration data
        rsvp_response = None
        if registration.additional_data:
            rsvp_response = registration.additional_data.get("rsvp_response")

        if form.button_type == "rsvp_yes_no" and rsvp_response == "no":
            subject = f"Thanks for letting us know - {form.title}"
            body = f"""Hi {registration.name},

Thanks for letting us know you can't make it to {form.title} on {form.event_date.strftime('%B %d, %Y')}.

We'll miss you! If you change your mind, you can always update your RSVP.

Best regards"""
        else:
            # RSVP yes or regular registration
            subject = f"You're registered for {form.title}"
            body = f"""Hi {registration.name},

You're all set for {form.title}!

Event Details:
📅 Date: {form.event_date.strftime('%B %d, %Y')}"""

            if form.start_time:
                time_str = form.start_time.strftime("%I:%M %p")
                if form.end_time:
                    time_str += f" - {form.end_time.strftime('%I:%M %p')}"
                body += f"\n🕐 Time: {time_str}"

            body += f"\n📍 Location: {form.location}"

            if form.description:
                body += f"\n\n{form.description}"

            body += "\n\nLooking forward to seeing you there!"

        return {"subject": subject, "body": body}

    async def _send_email(self, to_email: str, email_content: Dict[str, str]) -> bool:
        """Send email using the email client"""
        try:
            await self.email_client.send_email(
                to=to_email,
                text=email_content["body"],
                subject=email_content["subject"],
            )
            logger.info(f"Email sent successfully to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False
