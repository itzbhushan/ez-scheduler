import logging
from typing import Dict, Optional

from mailgun.client import Client

logger = logging.getLogger(__name__)


class EmailClient:
    def __init__(self, config: dict):
        self.mailgun_api_key = config["mailgun_api_key"]
        self.domain = config["mailgun_domain"]
        self.sender_email = config["sender_email"]

        self.client = Client(auth=("api", self.mailgun_api_key))

    async def send_email(
        self, to: str, text: str, subject: Optional[str] = None
    ) -> Dict:
        """
        Send email using Mailgun API

        Args:
            to: Recipient email address
            text: Email body text
            subject: Email subject (optional, uses default if not provided)

        Returns:
            Dict containing Mailgun API response

        Raises:
            ValueError: If email address is invalid
            RuntimeError: If email sending fails
        """
        data = {
            "from": self.sender_email,
            "to": to,
            "subject": subject or "[SignupPro] Thanks for your RSVP!",
            "text": text,
            "o:tag": "registration-confirmation",
        }

        try:
            req = self.client.messages.create(data=data, domain=self.domain)
            response = req.json()

            # Check if request was successful
            if req.status_code != 200:
                logger.error(f"Mailgun API error: {req.status_code} - {response}")
                raise RuntimeError(f"Failed to send email: {response}")

            logger.info(
                f"Email sent successfully to {to}: {response.get('id', 'unknown')}"
            )
            return response

        except Exception as e:
            logger.error(f"Failed to send email to {to}: {str(e)}")
            raise RuntimeError(f"Email sending failed: {str(e)}") from e
