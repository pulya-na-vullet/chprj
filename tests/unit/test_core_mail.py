"""Mail sender: console fallback for dev, SMTP via env for prod."""

from email.message import EmailMessage
from typing import Any

import pytest

from neurolegal.core.config import Settings
from neurolegal.core.mail import ConsoleMailSender, SmtpMailSender, make_mail_sender


def _settings(**env: str) -> Settings:
    return Settings(_env_file=None, DATABASE_URL="postgresql://u:p@h/db", **env)


async def test_console_sender_logs_the_message(caplog: pytest.LogCaptureFixture) -> None:
    sender = ConsoleMailSender()
    with caplog.at_level("INFO"):
        await sender.send(
            to="user@example.com", subject="Подтвердите почту", body="https://x/verify?token=abc"
        )
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "user@example.com" in joined
    assert "Подтвердите почту" in joined
    assert "https://x/verify?token=abc" in joined


async def test_smtp_sender_sends_email_message(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, Any] = {}

    async def fake_send(message: EmailMessage, **kwargs: Any) -> None:
        sent["message"] = message
        sent["kwargs"] = kwargs

    monkeypatch.setattr("neurolegal.core.mail.aiosmtplib.send", fake_send)
    sender = SmtpMailSender(
        host="smtp.example.com",
        port=587,
        username="mailer",
        password="secret",
        sender="neurolegal <noreply@example.com>",
        starttls=True,
    )
    await sender.send(to="user@example.com", subject="Сброс пароля", body="ссылка")

    message = sent["message"]
    assert message["To"] == "user@example.com"
    assert message["From"] == "neurolegal <noreply@example.com>"
    assert message["Subject"] == "Сброс пароля"
    assert "ссылка" in message.get_content()
    assert sent["kwargs"] == {
        "hostname": "smtp.example.com",
        "port": 587,
        "username": "mailer",
        "password": "secret",
        "start_tls": True,
    }


async def test_smtp_sender_omits_credentials_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, Any] = {}

    async def fake_send(message: EmailMessage, **kwargs: Any) -> None:
        sent["kwargs"] = kwargs

    monkeypatch.setattr("neurolegal.core.mail.aiosmtplib.send", fake_send)
    sender = SmtpMailSender(
        host="relay.local", port=25, username=None, password=None, sender="a@b", starttls=False
    )
    await sender.send(to="user@example.com", subject="s", body="b")
    assert sent["kwargs"] == {"hostname": "relay.local", "port": 25, "start_tls": False}


def test_factory_returns_console_without_smtp_host() -> None:
    assert isinstance(make_mail_sender(_settings()), ConsoleMailSender)


def test_factory_returns_smtp_with_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEUROLEGAL_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("NEUROLEGAL_SMTP_FROM", "noreply@example.com")
    assert isinstance(make_mail_sender(_settings()), SmtpMailSender)


def test_factory_requires_from_when_smtp_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEUROLEGAL_SMTP_HOST", "smtp.example.com")
    with pytest.raises(ValueError, match="NEUROLEGAL_SMTP_FROM"):
        make_mail_sender(_settings())


def test_settings_smtp_defaults() -> None:
    s = _settings()
    assert s.smtp_host is None
    assert s.smtp_port == 587
    assert s.smtp_user is None
    assert s.smtp_password is None
    assert s.smtp_from is None
    assert s.smtp_starttls is True
    assert s.public_base_url == "http://127.0.0.1:8000"
