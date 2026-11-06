"""Safaricom Daraja (M-Pesa Express) client.

The immediate STK response only means the prompt was sent; it is never treated as
payment. A sale is created only after the callback is verified against the STK push
query endpoint, or after an explicit status query confirms success.
"""

import base64
import time
from datetime import datetime

import requests

from .config import (
    APP_ENV,
    MPESA_BASE_URL,
    MPESA_CALLBACK_TOKEN,
    MPESA_CALLBACK_URL,
    MPESA_CONSUMER_KEY,
    MPESA_CONSUMER_SECRET,
    MPESA_PASSKEY,
    MPESA_SHORTCODE,
    MPESA_SIMULATE,
    MPESA_TRANSACTION_TYPE,
)

_token_cache: dict[str, float | str | None] = {"value": None, "expires_at": 0.0}
REQUEST_TIMEOUT = 25


class MpesaError(Exception):
    pass


def mpesa_configured() -> bool:
    return all([MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET, MPESA_PASSKEY, MPESA_SHORTCODE])


def simulation_enabled() -> bool:
    return MPESA_SIMULATE and APP_ENV != "production"


def callback_url() -> str:
    base = MPESA_CALLBACK_URL.rstrip("/")
    if MPESA_CALLBACK_TOKEN and not base.endswith(f"/{MPESA_CALLBACK_TOKEN}"):
        return f"{base}/{MPESA_CALLBACK_TOKEN}"
    return base


def normalise_phone(raw: str) -> str:
    digits = "".join(character for character in str(raw) if character.isdigit())
    if digits.startswith("254") and len(digits) == 13 and digits[3] == "0":
        digits = "254" + digits[4:]
    if digits.startswith("254") and len(digits) == 12:
        return digits
    if digits.startswith("0") and len(digits) == 10:
        return "254" + digits[1:]
    if digits[:1] in {"7", "1"} and len(digits) == 9:
        return "254" + digits
    raise MpesaError("Enter the M-Pesa phone as 07XXXXXXXX or 2547XXXXXXXX.")


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")


def _password(timestamp: str) -> str:
    raw = f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}".encode("utf-8")
    return base64.b64encode(raw).decode("utf-8")


def access_token() -> str:
    cached = _token_cache.get("value")
    if cached and time.time() < float(_token_cache.get("expires_at") or 0):
        return str(cached)

    try:
        response = requests.get(
            f"{MPESA_BASE_URL}/oauth/v1/generate",
            params={"grant_type": "client_credentials"},
            auth=(MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET),
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        raise MpesaError("Could not reach Safaricom Daraja. Check the API server's internet access.")

    if response.status_code >= 400:
        raise MpesaError("Safaricom rejected the M-Pesa consumer key or secret.")
    try:
        payload = response.json()
        token = payload["access_token"]
        expires_in = int(payload.get("expires_in", 3599))
    except (ValueError, KeyError, TypeError):
        raise MpesaError("Safaricom returned an unexpected token response.")

    _token_cache["value"] = token
    _token_cache["expires_at"] = time.time() + max(expires_in - 60, 60)
    return token


def stk_push(phone: str, amount: int, reference: str, description: str) -> dict:
    timestamp = _timestamp()
    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": _password(timestamp),
        "Timestamp": timestamp,
        "TransactionType": MPESA_TRANSACTION_TYPE,
        "Amount": int(amount),
        "PartyA": phone,
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": phone,
        "CallBackURL": callback_url(),
        "AccountReference": reference[:12],
        "TransactionDesc": description[:60],
    }

    try:
        response = requests.post(
            f"{MPESA_BASE_URL}/mpesa/stkpush/v1/processrequest",
            json=payload,
            headers={"Authorization": f"Bearer {access_token()}"},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        raise MpesaError("Could not reach Safaricom to send the payment prompt.")

    try:
        data = response.json()
    except ValueError:
        raise MpesaError(f"Safaricom returned an unexpected response ({response.status_code}).")

    if response.status_code >= 400 or str(data.get("ResponseCode")) != "0":
        message = data.get("errorMessage") or data.get("ResponseDescription") or "STK push was rejected."
        raise MpesaError(str(message))

    return {
        "checkout_request_id": data.get("CheckoutRequestID"),
        "merchant_request_id": data.get("MerchantRequestID"),
        "customer_message": data.get("CustomerMessage") or "Payment prompt sent to the customer.",
    }


def query_status(checkout_request_id: str) -> dict:
    timestamp = _timestamp()
    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": _password(timestamp),
        "Timestamp": timestamp,
        "CheckoutRequestID": checkout_request_id,
    }

    try:
        response = requests.post(
            f"{MPESA_BASE_URL}/mpesa/stkpushquery/v1/query",
            json=payload,
            headers={"Authorization": f"Bearer {access_token()}"},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        raise MpesaError("Could not verify the payment with Safaricom.")

    try:
        data = response.json()
    except ValueError:
        raise MpesaError(f"Safaricom returned an unexpected response ({response.status_code}).")

    if response.status_code >= 400:
        message = data.get("errorMessage") or "Could not verify the payment."
        raise MpesaError(str(message))

    return {
        "result_code": str(data.get("ResultCode", "")),
        "result_desc": data.get("ResultDesc") or "",
        "merchant_request_id": data.get("MerchantRequestID"),
        "checkout_request_id": data.get("CheckoutRequestID"),
    }
