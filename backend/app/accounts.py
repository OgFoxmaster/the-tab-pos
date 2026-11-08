"""Owner onboarding and password recovery.

Owner self-registration exists so a shop can claim its owner account from the login
screen instead of shipping with a seeded password. It is only available when no owner
exists yet or when the email is explicitly allow-listed, and it can additionally
require a shared signup code.
"""

import hashlib
import re
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import (
    APP_ENV,
    LOGIN_CODE_EXPIRES_MINUTES,
    LOGIN_CODE_LENGTH,
    APP_WEB_URL,
    OWNER_SIGNUP_CODE,
    OWNER_SIGNUP_EMAILS,
    PASSWORD_RESET_MINUTES,
    RESET_CODE_EXPIRES_MINUTES,
    RESET_CODE_LENGTH,
)
from .db import get_db
from .email_service import mailtrap_configured, send_code_email, send_password_reset_email, send_sms_code
from .models import Branch, Company, PasswordReset, User
from .reports import utcnow
from .schemas import (
    ChangePassword,
    ForgotPassword,
    OwnerRegister,
    ResetPassword,
    TokenResponse,
)
from .security import create_access_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["accounts"])


def _owner_exists(db: Session) -> bool:
    return db.query(User).filter(User.role == "owner").first() is not None


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def make_code(length: int) -> str:
    return f"{secrets.randbelow(10 ** length):0{length}d}"


def deliver_code(user: User, code: str, purpose: str) -> str | None:
    if user.phone and send_sms_code(user.phone, code, purpose):
        return "sms"
    if user.email and send_code_email(user.email, user.full_name, code, purpose):
        return "email"
    return None


def _unique_username(db: Session, email: str) -> str:
    base = re.sub(r"[^a-z0-9._-]", "", email.split("@")[0].lower())[:40] or "owner"
    candidate = base
    suffix = 1
    while db.query(User).filter(User.username == candidate).first():
        suffix += 1
        candidate = f"{base}{suffix}"
    return candidate


@router.get("/setup-status")
def setup_status(db: Session = Depends(get_db)):
    owner_exists = _owner_exists(db)
    allowlist_open = bool(OWNER_SIGNUP_EMAILS)
    return {
        "owner_exists": owner_exists,
        "signup_open": (not owner_exists) or allowlist_open,
        "requires_code": bool(OWNER_SIGNUP_CODE),
        "email_reset_configured": mailtrap_configured(),
        "phone_reset_enabled": RESET_CODE_LENGTH > 0,
        "login_code_required": LOGIN_CODE_LENGTH > 0,
        "sms_configured": bool(user_sms_configured()),
    }


@router.post("/register-owner", response_model=TokenResponse)
def register_owner(payload: OwnerRegister, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()

    if OWNER_SIGNUP_EMAILS and email not in OWNER_SIGNUP_EMAILS:
        raise HTTPException(status_code=403, detail="This email is not allowed to create the owner account.")
    if _owner_exists(db) and not OWNER_SIGNUP_EMAILS:
        raise HTTPException(
            status_code=403,
            detail="The owner account already exists. Ask the owner to create a staff account for you.",
        )
    if OWNER_SIGNUP_CODE and (payload.signup_code or "").strip() != OWNER_SIGNUP_CODE:
        raise HTTPException(status_code=403, detail="The owner signup code is incorrect.")
    if db.query(User).filter(func.lower(User.email) == email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists.")

    username = _unique_username(db, email)
    slug_base = re.sub(r"[^a-z0-9]+", "-", payload.company_name.lower()).strip("-") or "company"
    slug = slug_base
    suffix = 1
    while db.query(Company).filter(Company.slug == slug).first():
        suffix += 1
        slug = f"{slug_base}-{suffix}"
    company = Company(name=payload.company_name.strip(), slug=slug)
    db.add(company)
    db.flush()
    branch = Branch(company_id=company.id, name=payload.branch_name.strip(), address=payload.branch_address)
    db.add(branch)
    db.flush()

    user = User(
        company_id=company.id,
        branch_id=branch.id,
        username=username,
        email=email,
        phone=payload.phone,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role="owner",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "access_token": create_access_token(user.username, user.role),
        "token_type": "bearer",
        "role": user.role,
        "username": user.username,
    }


def user_sms_configured() -> bool:
    from .config import SMS_API_TOKEN, SMS_API_URL
    return bool(SMS_API_URL and SMS_API_TOKEN)


@router.post("/forgot-password")
def forgot_password(payload: ForgotPassword, db: Session = Depends(get_db)):
    email = (payload.email or "").strip().lower()
    phone = payload.phone.strip() if payload.phone else None
    if not email and not phone:
        raise HTTPException(status_code=400, detail="Enter the account email or registered phone number.")

    user_query = db.query(User)
    if email and phone:
        user_query = user_query.filter((func.lower(User.email) == email) | (User.phone == phone))
    elif email:
        user_query = user_query.filter(func.lower(User.email) == email)
    else:
        user_query = user_query.filter(User.phone == phone)
    user = user_query.first()

    if not user or not user.is_active:
        return {"message": "If that account exists, a reset code has been sent."}

    email_configured = mailtrap_configured()
    if phone and user.phone and phone != user.phone:
        raise HTTPException(status_code=400, detail="That phone number is not registered on this account.")
    if phone and not user.phone:
        raise HTTPException(status_code=400, detail="No phone number is registered. Ask the owner to add it in Users.")
    reset = PasswordReset(
        user_id=user.id,
        token_hash=secrets.token_urlsafe(32),
        expires_at=utcnow() + timedelta(minutes=PASSWORD_RESET_MINUTES),
    )
    db.add(reset)
    db.commit()

    if phone and RESET_CODE_LENGTH > 0:
        code = make_code(RESET_CODE_LENGTH)
        reset.token_hash = code
        reset.expires_at = utcnow() + timedelta(minutes=RESET_CODE_EXPIRES_MINUTES)
        db.commit()
        if not send_sms_code(user.phone, code, "password reset"):
            if APP_ENV == "production":
                raise HTTPException(status_code=503, detail="SMS reset is not configured on the server.")
            return {"message": "Development reset code generated.", "channel": "sms", "dev_reset_token": code, "code_length": RESET_CODE_LENGTH}
        return {
            "message": "A reset code has been sent to your phone.",
            "channel": "sms",
            "phone": phone,
            "code_length": RESET_CODE_LENGTH,
            "expires_minutes": RESET_CODE_EXPIRES_MINUTES,
        }

    link = f"{APP_WEB_URL.rstrip('/')}/?reset={reset.token_hash}"
    sent = send_password_reset_email(user.email, user.full_name, link)

    if not sent:
        if APP_ENV == "production":
            raise HTTPException(
                status_code=503,
                detail="Password reset email delivery failed. Check the Mailtrap SMTP token, verified sender, and Email Logs.",
            )
        return {
            "message": "If that account exists, a password reset link has been sent.",
            "email_configured": False,
            "dev_reset_link": link,
            "dev_reset_token": reset.token_hash,
        }

    return {"message": "If that account exists, a password reset link has been sent.", "email_configured": email_configured}


@router.post("/reset-password")
def reset_password(payload: ResetPassword, db: Session = Depends(get_db)):
    reset = (
        db.query(PasswordReset)
        .filter(PasswordReset.token_hash == payload.token, PasswordReset.used_at.is_(None))
        .first()
    )
    if not reset or reset.expires_at < utcnow():
        raise HTTPException(status_code=400, detail="This reset code is invalid or has expired.")

    user = db.query(User).filter(User.id == reset.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="This reset code no longer valid.")

    user.password_hash = hash_password(payload.password)
    reset.used_at = utcnow()
    db.query(PasswordReset).filter(
        PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None)
    ).update({"used_at": utcnow()})
    db.commit()

    return {"message": "Password updated. You can sign in with the new password."}


@router.post("/change-password")
def change_password(
    payload: ChangePassword,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="The current password is incorrect.")
    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"message": "Password updated."}
