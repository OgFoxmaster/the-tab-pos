import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

APP_NAME = "The Tab POS"
APP_VERSION = "2.0.0"
APP_ENV = os.getenv("APP_ENV", "development")
DEBUG = APP_ENV != "production"

DEFAULT_DATABASE_URL = f"sqlite:///{BASE_DIR / 'data' / 'thetabpos.db'}"


def normalise_database_url(url: str) -> str:
    """Render, Heroku and Vercel hand out plain postgres:// URLs; psycopg 3 needs its dialect."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = normalise_database_url(os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL))
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

DEFAULT_JWT_SECRET = "change-me-in-production"
JWT_SECRET = os.getenv("JWT_SECRET", DEFAULT_JWT_SECRET)
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
SEED_DEMO_DATA = os.getenv("SEED_DEMO_DATA", "true").lower() not in {"0", "false", "no"}

# Store identity used on receipts, reports and the AI prompt.
STORE_NAME = os.getenv("STORE_NAME", "The Tab")
STORE_TAGLINE = os.getenv("STORE_TAGLINE", "Liquor Store")
STORE_ADDRESS = os.getenv("STORE_ADDRESS", "Nairobi, Kenya")
STORE_PHONE = os.getenv("STORE_PHONE", "+254 700 000 000")
STORE_CURRENCY = os.getenv("STORE_CURRENCY", "KES")
STORE_RECEIPT_FOOTER = os.getenv(
    "STORE_RECEIPT_FOOTER", "Thank you for shopping with The Tab. Drink responsibly."
)

# Retail prices are treated as VAT-inclusive. Set VAT_RATE=0 to disable the breakdown.
VAT_RATE = float(os.getenv("VAT_RATE", "0.16"))

# AI analyst. Any OpenAI-compatible chat-completions provider works; Z.ai is the default.
AI_API_KEY = os.getenv("ZAI_API_KEY") or os.getenv("AI_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
AI_BASE_URL = os.getenv("ZAI_API_BASE") or os.getenv("AI_BASE_URL") or "https://api.z.ai/api/paas/v4"
AI_MODEL = os.getenv("AI_MODEL", "glm-4-flash")
AI_DAILY_LIMIT = int(os.getenv("AI_DAILY_LIMIT", "40"))
AI_TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", "30"))
AI_ALLOWED_MODELS = {"glm-4-flash", "glm-4-air", "glm-4-plus", "glm-4.6", "gpt-4o-mini"}

# Web research for the AI analyst. Optional: without a key the assistant still
# answers from the store's own figures, only the web-lookup does not.
EXA_API_KEY = os.getenv("EXA_API_KEY", "")
EXA_NUM_RESULTS = int(os.getenv("EXA_NUM_RESULTS", "5"))
EXA_TIMEOUT_SECONDS = int(os.getenv("EXA_TIMEOUT_SECONDS", "20"))

# Offline checkouts are queued on the till and replayed later. Keep this window generous
# enough for a day of trading but small enough to reject stale or forged timestamps.
OFFLINE_SALE_MAX_AGE_DAYS = int(os.getenv("OFFLINE_SALE_MAX_AGE_DAYS", "14"))
OFFLINE_SALE_MAX_FUTURE_MINUTES = int(os.getenv("OFFLINE_SALE_MAX_FUTURE_MINUTES", "10"))

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


# Owner self-registration. Leave the allowlist empty to only allow the first claim.
OWNER_SIGNUP_EMAILS = [
    email.strip().lower()
    for email in os.getenv("OWNER_SIGNUP_EMAILS", "").split(",")
    if email.strip()
]
OWNER_SIGNUP_CODE = os.getenv("OWNER_SIGNUP_CODE", "")

APP_WEB_URL = os.getenv("APP_WEB_URL", CORS_ORIGINS[0] if CORS_ORIGINS else "http://localhost:5173")
PASSWORD_RESET_MINUTES = int(os.getenv("PASSWORD_RESET_MINUTES", "30"))
# Phone reset code: 0 = email only (current behaviour), 6 = six-digit code.
RESET_CODE_LENGTH = int(os.getenv("RESET_CODE_LENGTH", "0"))
RESET_CODE_EXPIRES_MINUTES = int(os.getenv("RESET_CODE_EXPIRES_MINUTES", "15"))
# Require a one-time code after every successful password check. Set to 0 to disable.
LOGIN_CODE_LENGTH = int(os.getenv("LOGIN_CODE_LENGTH", "6"))
LOGIN_CODE_EXPIRES_MINUTES = int(os.getenv("LOGIN_CODE_EXPIRES_MINUTES", "10"))
# Optional SMS gateway: POST JSON {"to": phone, "message": text} with Bearer auth.
SMS_API_URL = os.getenv("SMS_API_URL", "")
SMS_API_TOKEN = os.getenv("SMS_API_TOKEN", "")


# Password reset email (Gmail app password or any SMTP provider).
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USERNAME)
SMTP_STARTTLS = os.getenv("SMTP_STARTTLS", "true").lower() in {"1", "true", "yes"}
SMTP_SSL = os.getenv("SMTP_SSL", "false").lower() in {"1", "true", "yes"}

MPESA_CALLBACK_TOKEN = os.getenv("MPESA_CALLBACK_TOKEN", "")
MPESA_TRANSACTION_TYPE = os.getenv("MPESA_TRANSACTION_TYPE", "CustomerPayBillOnline")
MPESA_SIMULATE = os.getenv("MPESA_SIMULATE", "false").lower() in {"1", "true", "yes"}


def resolved_ai_model() -> str:
    return AI_MODEL if AI_MODEL in AI_ALLOWED_MODELS else "glm-4-flash"


def assert_production_safety() -> None:
    """Refuse to boot production with placeholder credentials."""
    if APP_ENV != "production":
        return

    problems = []
    if JWT_SECRET == DEFAULT_JWT_SECRET or len(JWT_SECRET) < 32:
        problems.append(
            "JWT_SECRET must be a unique random value of at least 32 characters in production."
        )
    if not CORS_ORIGINS:
        problems.append("CORS_ORIGINS must list the deployed web origin in production.")

    if problems:
        raise RuntimeError("Refusing to start in production: " + " ".join(problems))

    if not SMTP_HOST:
        print(
            "WARNING: SMTP is not configured; password reset emails will not be delivered.",
            file=sys.stderr,
        )

    if SEED_DEMO_DATA and (OWNER_PASSWORD == "Owner@123" or MANAGER_PASSWORD == "Manager@123"):
        print(
            "WARNING: default staff passwords are still active. Change OWNER_PASSWORD, "
            "MANAGER_PASSWORD, CASHIER_PASSWORD and STOCK_PASSWORD before going live.",
            file=sys.stderr,
        )
