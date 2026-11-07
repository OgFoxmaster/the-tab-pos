"""Password reset email delivery over SMTP.

Works with a Gmail app password (smtp.gmail.com:587 + STARTTLS) or any SMTP provider.
No third-party SDK or vendor account is required beyond the mailbox itself.
"""

import smtplib
import ssl

import requests
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
    SMS_API_TOKEN,
    SMS_API_URL,
)


def smtp_configured() -> bool:
    return bool(SMTP_HOST and SMTP_FROM)


def send_code_email(to_email: str, name: str, code: str, purpose: str = "login") -> bool:
    if not smtp_configured():
        return False

    message = EmailMessage()
    message["Subject"] = f"Your {STORE_NAME} verification code"
    message["From"] = SMTP_FROM
    message["To"] = to_email
    message.set_content(
        f"Hello {name},\n\nYour {STORE_NAME} {purpose} code is: {code}\n\n"
        "This code expires soon and can be used once. If you did not request it, ignore this message.\n"
    )
    try:
        if SMTP_SSL:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
            if SMTP_STARTTLS:
                server.starttls(context=ssl.create_default_context())
        with server:
            if SMTP_USERNAME:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(message)
        return True
    except Exception as error:
        print(f"Verification email could not be sent: {error}")
        return False


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
