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
    APP_WEB_URL,
    OWNER_SIGNUP_CODE,
    OWNER_SIGNUP_EMAILS,
    PASSWORD_RESET_MINUTES,
)
from .db import get_db
from .email_service import send_password_reset_email, smtp_configured
from .models import PasswordReset, User
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
        "email_reset_configured": smtp_configured(),
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
    user = User(
        username=username,
        email=email,
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


@router.post("/forgot-password")
def forgot_password(payload: ForgotPassword, db: Session = Depends(get_db)):
    generic = {"message": "If that account exists, a password reset link has been sent."}
    email = payload.email.strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()

    if not user or not user.is_active:
        return generic

    token = secrets.token_urlsafe(32)
    reset = PasswordReset(
        user_id=user.id,
        token_hash=_hash_token(token),
        expires_at=utcnow() + timedelta(minutes=PASSWORD_RESET_MINUTES),
    )
    db.add(reset)
    db.commit()

    link = f"{APP_WEB_URL.rstrip('/')}/?reset={token}"
    sent = send_password_reset_email(user.email, user.full_name, link)

    if not sent:
        if APP_ENV == "production":
            raise HTTPException(
                status_code=503,
                detail="Password reset email is not configured on the server. Ask the owner to reset your password.",
            )
        # Development convenience only: never return the token in production.
        return {
            **generic,
            "email_configured": False,
            "dev_reset_link": link,
            "dev_reset_token": token,
        }

    return {**generic, "email_configured": True}


@router.post("/reset-password")
def reset_password(payload: ResetPassword, db: Session = Depends(get_db)):
    reset = (
        db.query(PasswordReset)
        .filter(PasswordReset.token_hash == _hash_token(payload.token), PasswordReset.used_at.is_(None))
        .first()
    )
    if not reset or reset.expires_at < utcnow():
        raise HTTPException(status_code=400, detail="This reset link is invalid or has expired.")

    user = db.query(User).filter(User.id == reset.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="This reset link is no longer valid.")

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
