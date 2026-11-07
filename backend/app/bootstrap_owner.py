from sqlalchemy.orm import Session

from .config import (
    CASHIER_EMAIL,
    CASHIER_PASSWORD,
    MANAGER_EMAIL,
    MANAGER_PASSWORD,
    OWNER_EMAIL,
    OWNER_PASSWORD,
    SEED_DEMO_DATA,
    STOCK_EMAIL,
    STOCK_PASSWORD,
)
from .db import SessionLocal
from .models import Branch, Company, User
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
    # A real shop starts empty and claims its owner account from the login screen.
    # Demo accounts are only for development or an explicit SEED_DEMO_DATA=true.
    if not SEED_DEMO_DATA:
        print("Skipping default accounts; the owner can register from the login screen")
        return

    db: Session = SessionLocal()
    try:
        company = db.query(Company).first()
        if company is None:
            company = Company(name="The Tab Demo Company", slug="the-tab-demo")
            db.add(company)
            db.flush()
        branch = db.query(Branch).filter(Branch.company_id == company.id).first()
        if branch is None:
            branch = Branch(company_id=company.id, name="Main Branch")
            db.add(branch)
            db.flush()
        for user_config in DEFAULT_USERS:
            user = db.query(User).filter(User.username == user_config["username"]).first()
            if user is None:
                db.add(
                    User(
                        company_id=company.id,
                        branch_id=branch.id,
                        username=user_config["username"],
                        email=user_config["email"],
                        full_name=user_config["full_name"],
                        password_hash=hash_password(user_config["password"]),
                        role=user_config["role"],
                        department="stock_manager" if user_config["role"] == "stock" else user_config["role"],
                        is_active=True,
                    )
                )
        # Attach legacy rows to the seeded tenant so old development data remains usable.
        for model in (User,):
            db.query(model).filter(model.company_id.is_(None)).update({"company_id": company.id, "branch_id": branch.id}, synchronize_session=False)
        for model in ("products", "sales", "expenses", "stock_movements", "audit_events"):
            db.execute(__import__("sqlalchemy").text(f"UPDATE {model} SET company_id=:company_id, branch_id=:branch_id WHERE company_id IS NULL"), {"company_id": company.id, "branch_id": branch.id})
        db.commit()
        print("Ensured default POS accounts")
    finally:
        db.close()
