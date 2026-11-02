import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

APP_NAME = "The Tab POS"
APP_ENV = os.getenv("APP_ENV", "development")
DEBUG = APP_ENV != "production"

DEFAULT_DATABASE_URL = f"sqlite:///{BASE_DIR / 'data' / 'thetabpos.db'}"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

OWNER_EMAIL = os.getenv("OWNER_EMAIL", "owner@thetab.co.ke")
OWNER_PASSWORD = os.getenv("OWNER_PASSWORD", "Owner@123")
MANAGER_EMAIL = os.getenv("MANAGER_EMAIL", "manager@thetab.co.ke")
MANAGER_PASSWORD = os.getenv("MANAGER_PASSWORD", "Manager@123")
CASHIER_EMAIL = os.getenv("CASHIER_EMAIL", "cashier@thetab.co.ke")
CASHIER_PASSWORD = os.getenv("CASHIER_PASSWORD", "Cashier@123")
STOCK_EMAIL = os.getenv("STOCK_EMAIL", "stock@thetab.co.ke")
STOCK_PASSWORD = os.getenv("STOCK_PASSWORD", "Stock@123")

MPESA_ENV = os.getenv("MPESA_ENV", "sandbox")
MPESA_CONSUMER_KEY = os.getenv("MPESA_CONSUMER_KEY", "")
MPESA_CONSUMER_SECRET = os.getenv("MPESA_CONSUMER_SECRET", "")
MPESA_SHORTCODE = os.getenv("MPESA_SHORTCODE", "174379")
MPESA_PASSKEY = os.getenv("MPESA_PASSKEY", "")
MPESA_CALLBACK_URL = os.getenv("MPESA_CALLBACK_URL", f"{APP_BASE_URL}/mpesa/callback")
MPESA_TIMEOUT_URL = os.getenv("MPESA_TIMEOUT_URL", f"{APP_BASE_URL}/mpesa/timeout")
MPESA_BASE_URL = os.getenv(
    "MPESA_BASE_URL",
    "https://sandbox.safaricom.co.ke" if MPESA_ENV == "sandbox" else "https://api.safaricom.co.ke",
)
