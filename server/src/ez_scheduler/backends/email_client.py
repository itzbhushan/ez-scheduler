from mailgun.client import Client


class EmailClient:
    def __init__(self, config: dict):
        key = config["mailgun_api_key"]
        self.domain = config["mailgun_domain"]
        self.client = Client(auth=("api", key))
        self.sender_email = config["sender_email"]

    def send_email(self, to: str, text: str) -> dict:
        data = {
            "from": self.sender_email,
            "to": to,
            "subject": "[SignupPro] Your registration is confirmed!",
            "text": text,
            "o:tag": "Python test",
        }

        req = self.client.messages.create(data=data, domain=self.domain)
        return req.json()
