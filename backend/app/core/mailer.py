"""Outgoing email (optional, A6). Without SMTP_HOST nothing is sent and every
flow still works: Admins hand out set-password links themselves (FR-AUTH-02).

Message bodies are never logged.
"""

import asyncio
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from fastapi import Request

from app.core.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Email:
    to: str
    subject: str
    body: str


class Mailer(Protocol):
    @property
    def enabled(self) -> bool: ...

    async def send(self, email: Email) -> bool:
        """Send; return False (and log) on failure instead of raising."""
        ...


class DisabledMailer:
    enabled = False

    async def send(self, email: Email) -> bool:
        logger.info("email_not_sent_smtp_disabled")
        return False


class SmtpMailer:
    enabled = True

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send(self, email: Email) -> bool:
        try:
            await asyncio.to_thread(self._send_sync, email)
        except OSError, smtplib.SMTPException:
            logger.warning("email_send_failed", exc_info=True)
            return False
        logger.info("email_sent")
        return True

    def _send_sync(self, email: Email) -> None:
        s = self._settings
        message = EmailMessage()
        message["From"] = s.smtp_from
        message["To"] = email.to
        message["Subject"] = email.subject
        message.set_content(email.body)
        assert s.smtp_host is not None  # noqa: S101 - guarded by create_mailer
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds) as smtp:
            if s.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if s.smtp_username and s.smtp_password:
                smtp.login(s.smtp_username, s.smtp_password)
            smtp.send_message(message)


def create_mailer(settings: Settings) -> Mailer:
    return SmtpMailer(settings) if settings.smtp_enabled else DisabledMailer()


def get_mailer(request: Request) -> Mailer:
    mailer: Mailer = request.app.state.mailer
    return mailer
