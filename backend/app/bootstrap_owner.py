from sqlalchemy.orm import Session

from .config import (
    CASHIER_EMAIL,
    CASHIER_PASSWORD,
    MANAGER_EMAIL,
    MANAGER_PASSWORD,
    OWNER_EMAIL,
    OWNER_PASSWORD,
    STOCK_EMAIL,
    STOCK_PASSWORD,
)
from .db import SessionLocal
from .models import User
from .security import hash_password


DEFAULT_USERS = [
    {
        "username": "owner",
        "email": OWNER_EMAIL,
        "full_name": "Business Owner",
        "password": OWNER_PASSWORD,
        "role": "owner",
    },
    {
        "username": "manager",
        "email": MANAGER_EMAIL,
        "full_name": "Branch Manager",
        "password": MANAGER_PASSWORD,
        "role": "manager",
    },
    {
        "username": "cashier",
        "email": CASHIER_EMAIL,
        "full_name": "Front Desk Cashier",
        "password": CASHIER_PASSWORD,
        "role": "cashier",
    },
    {
        "username": "stock",
        "email": STOCK_EMAIL,
        "full_name": "Inventory Controller",
        "password": STOCK_PASSWORD,
        "role": "stock",
    },
]


def ensure_owner() -> None:
    db: Session = SessionLocal()
    try:
        for user_config in DEFAULT_USERS:
            user = db.query(User).filter(User.username == user_config["username"]).first()
            if user is None:
                db.add(
                    User(
                        username=user_config["username"],
                        email=user_config["email"],
                        full_name=user_config["full_name"],
                        password_hash=hash_password(user_config["password"]),
                        role=user_config["role"],
                        is_active=True,
                    )
                )
        db.commit()
        print("Ensured default POS accounts")
    finally:
        db.close()
