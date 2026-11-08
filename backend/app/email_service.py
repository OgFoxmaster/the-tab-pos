"""Transactional email delivery through Mailtrap SMTP."""

import smtplib
from email.message import EmailMessage

import requests

from .config import (
    MAILTRAP_API_TOKEN,
    MAILTRAP_FROM,
    MAILTRAP_FROM_NAME,
    MAILTRAP_HOST,
    MAILTRAP_PORT,
    MAILTRAP_USERNAME,
    PASSWORD_RESET_MINUTES,
    STORE_NAME,
    SMS_API_TOKEN,
    SMS_API_URL,
)


def mailtrap_configured() -> bool:
    return bool(MAILTRAP_API_TOKEN and MAILTRAP_FROM)


def _send_email(to_email: str, name: str, subject: str, text: str) -> bool:
    if not mailtrap_configured():
        return False

    sender = f"{MAILTRAP_FROM_NAME} <{MAILTRAP_FROM}>"
    recipient = f"{name} <{to_email}>" if name else to_email
    message = EmailMessage()
    message["Subject"] = subject
    message["To"] = recipient
    message["From"] = sender
    message.set_content(text)

    try:
        with smtplib.SMTP(MAILTRAP_HOST, MAILTRAP_PORT, timeout=20) as server:
            server.starttls()
            server.login(MAILTRAP_USERNAME, MAILTRAP_API_TOKEN)
            server.send_message(message)
        return True
    except smtplib.SMTPAuthenticationError as error:
        # The SMTP token, username, or sender was rejected.
        print(f"Mailtrap SMTP authentication failed: {error}")
        return False
    except Exception as error:
        # Other delivery failures must not expose account existence or stop the API.
        print(f"Mailtrap email could not be sent: {error}")
        return False


def send_code_email(to_email: str, name: str, code: str, purpose: str = "login") -> bool:
    return _send_email(
        to_email,
        name,
        f"Your {STORE_NAME} verification code",
        f"Hello {name},\n\n"
        f"Your {STORE_NAME} {purpose} code is: {code}\n\n"
        "This code expires soon and can be used once. If you did not request it, ignore this message.\n",
    )


def send_sms_code(phone: str, code: str, purpose: str = "login") -> bool:
    if not SMS_API_URL or not SMS_API_TOKEN:
        return False
    try:
        response = requests.post(
            SMS_API_URL,
            json={"to": phone, "message": f"{STORE_NAME} {purpose} code: {code}"},
            headers={"Authorization": f"Bearer {SMS_API_TOKEN}"},
            timeout=15,
        )
        response.raise_for_status()
        return True
    except Exception as error:
        print(f"Verification SMS could not be sent: {error}")
        return False


def send_password_reset_email(to_email: str, name: str, link: str) -> bool:
    return _send_email(
        to_email,
        name,
        f"Reset your {STORE_NAME} POS password",
        f"Hello {name},\n\n"
        f"Use this link to choose a new {STORE_NAME} POS password:\n\n{link}\n\n"
        f"The link expires in {PASSWORD_RESET_MINUTES} minutes and can be used once.\n"
        "If you did not request this, you can ignore this email.\n",
    )
