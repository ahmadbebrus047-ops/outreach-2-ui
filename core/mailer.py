"""
Gmail sender using the official Gmail API (OAuth), which is the right way to
send from a Google account you own -- more deliverable and durable than SMTP
with an app password.

Setup (the "app on Google" step):
  1. Google Cloud Console -> new project -> enable the Gmail API.
  2. Create OAuth client credentials (Desktop app) -> download as
     credentials.json into the project root.
  3. First run opens a browser to authorize; a token.json is cached after.
"""
from __future__ import annotations

import base64
from email.mime.text import MIMEText

from core import config
from core.logging_setup import get_logger

log = get_logger("mailer")

_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


class GmailMailer:
    def __init__(self):
        self._service = None

    def _get_service(self):
        if self._service is not None:
            return self._service
        # Imported lazily so the data-fetch job doesn't need these deps.
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        if config.GOOGLE_TOKEN_FILE.exists():
            creds = Credentials.from_authorized_user_file(
                str(config.GOOGLE_TOKEN_FILE), _SCOPES
            )
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(config.GOOGLE_CREDENTIALS_FILE), _SCOPES
                )
                creds = flow.run_local_server(port=0)
            config.GOOGLE_TOKEN_FILE.write_text(creds.to_json())

        self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def send(self, to_email: str, subject: str, body: str) -> bool:
        try:
            service = self._get_service()
            msg = MIMEText(body)
            msg["to"] = to_email
            msg["from"] = f"{config.SENDER_NAME} <{config.SENDER_EMAIL}>"
            msg["subject"] = subject
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            service.users().messages().send(
                userId="me", body={"raw": raw}
            ).execute()
            log.info("Sent to %s", to_email)
            return True
        except Exception as exc:  # noqa: BLE001 - log and keep the batch alive
            log.error("Send failed for %s: %s", to_email, exc)
            return False


class ConsoleMailer:
    """Dry-run mailer for testing without touching Gmail."""

    def send(self, to_email: str, subject: str, body: str) -> bool:
        log.info("[DRY-RUN] -> %s | %s", to_email, subject)
        return True
