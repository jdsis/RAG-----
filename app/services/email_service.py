from __future__ import annotations

import smtplib
from email.header import Header
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import settings


class EmailNotConfiguredError(RuntimeError):
    pass


def send_email(to_email: str, subject: str, text: str) -> None:
    if not settings.smtp_host or not settings.smtp_username or not settings.smtp_password:
        raise EmailNotConfiguredError("SMTP mail service is not configured")

    message = EmailMessage()
    message["Subject"] = str(Header(subject, "utf-8"))
    message["From"] = formataddr(
        (str(Header(settings.smtp_from_name, "utf-8")), settings.smtp_from_email or settings.smtp_username)
    )
    message["To"] = to_email
    message.set_content(text, subtype="plain", charset="utf-8")

    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
