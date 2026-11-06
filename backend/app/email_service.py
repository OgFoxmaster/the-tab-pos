"""Password reset email delivery over SMTP.

Works with a Gmail app password (smtp.gmail.com:587 + STARTTLS) or any SMTP provider.
No third-party SDK or vendor account is required beyond the mailbox itself.
"""

import smtplib
import ssl
from email.message import EmailMessage

from .config import (
    PASSWORD_RESET_MINUTES,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_SSL,
    SMTP_STARTTLS,
    SMTP_USERNAME,
    STORE_NAME,
)


def smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_FROM)


def send_password_reset_email(to_email: str, name: str, link: str) -> bool:
    if not smtp_configured():
        return False

    message = EmailMessage()
    message["Subject"] = f"Reset your {STORE_NAME} POS password"
    message["From"] = SMTP_FROM
    message["To"] = to_email
    message.set_content(
        f"Hello {name},\n\n"
        f"Use this link to choose a new {STORE_NAME} POS password:\n\n{link}\n\n"
        f"The link expires in {PASSWORD_RESET_MINUTES} minutes and can be used once.\n"
        "If you did not request this, you can ignore this email.\n"
    )

    try:
        if SMTP_SSL:
            server = smtplib.SMTP_SSL(
                SMTP_HOST, SMTP_PORT, timeout=20, context=ssl.create_default_context()
            )
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
            if SMTP_STARTTLS:
                server.starttls(context=ssl.create_default_context())
        with server:
            if SMTP_USERNAME:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(message)
        return True
    except Exception as error:  # SMTP failures must never leak account existence.
        print(f"Password reset email could not be sent: {error}")
        return False
