"""Outbound mail: SMTP when configured, console (log) fallback for dev.

DORMANT since T-0026 (2026-07-11): the auth mail flows (email verification /
password-reset links) were removed, so nothing calls this at runtime. Kept
intact for when mail returns (e.g. self-service reset). The console fallback
still routes a message to the log when no SMTP is configured, so a future
mail-driven flow works on a fresh checkout without a provider.
"""

import logging
from email.message import EmailMessage
from typing import Any, Protocol

import aiosmtplib

from neurolegal.core.config import Settings

logger = logging.getLogger(__name__)


class MailSender(Protocol):
    async def send(self, *, to: str, subject: str, body: str) -> None: ...


class ConsoleMailSender:
    async def send(self, *, to: str, subject: str, body: str) -> None:
        logger.info("mail (console mode) to=%s subject=%s body=%s", to, subject, body)


class SmtpMailSender:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        sender: str,
        starttls: bool,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender
        self._starttls = starttls

    async def send(self, *, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        kwargs: dict[str, Any] = {
            "hostname": self._host,
            "port": self._port,
            "start_tls": self._starttls,
        }
        if self._username is not None:
            kwargs["username"] = self._username
        if self._password is not None:
            kwargs["password"] = self._password
        await aiosmtplib.send(message, **kwargs)


def make_mail_sender(settings: Settings) -> MailSender:
    if settings.smtp_host is None:
        return ConsoleMailSender()
    if settings.smtp_from is None:
        raise ValueError("NEUROLEGAL_SMTP_FROM is required when NEUROLEGAL_SMTP_HOST is set")
    return SmtpMailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password,
        sender=settings.smtp_from,
        starttls=settings.smtp_starttls,
    )
