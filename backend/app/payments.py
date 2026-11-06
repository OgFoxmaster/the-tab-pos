"""M-Pesa payment intents.

1. The till posts a basket and phone number; the API prices it, stores an intent and
   sends the STK prompt.
2. The customer approves on their phone. Safaricom posts a callback.
3. The callback is verified with the STK push query endpoint before a sale is created,
   so a forged callback cannot mark an order as paid. The till can also poll the intent
   or ask the server to verify it.
"""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .config import MPESA_CALLBACK_TOKEN, VAT_RATE
from .db import get_db
from .models import AuditEvent, PaymentIntent, Product, Sale, User
from .mpesa_service import (
    MpesaError,
    mpesa_configured,
    normalise_phone,
    query_status,
    simulation_enabled,
    stk_push,
)
from .sales_service import (
    InsufficientStock,
    UnknownProduct,
    money,
    persist_sale,
    price_basket,
    vat_component,
)
from .schemas import MpesaPaymentCreate
from .security import get_current_user, require_roles

router = APIRouter(tags=["mpesa"])

INTENT_TTL_MINUTES = 15


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _accepted() -> dict:
    return {"ResultCode": 0, "ResultDesc": "Accepted"}


def _intent_payload(intent: PaymentIntent, sale: Sale | None = None) -> dict:
    return {
        "reference": intent.reference,
        "status": intent.status,
        "amount": float(intent.amount),
        "phone": intent.phone,
        "mpesa_receipt": intent.mpesa_receipt,
        "result_desc": intent.result_desc,
        "problem": intent.problem,
        "checkout_request_id": intent.checkout_request_id,
        "created_at": intent.created_at.isoformat() if intent.created_at else None,
        "sale": {
            "sale_id": sale.id,
            "sale_number": sale.sale_number,
            "total": float(sale.total),
            "sale_time": sale.sale_time.isoformat() if sale.sale_time else None,
            "payment_method": sale.payment_method,
        } if sale else None,
    }


def _sale_for(db: Session, intent: PaymentIntent) -> Sale | None:
    if not intent.sale_id:
        return None
    return db.query(Sale).filter(Sale.id == intent.sale_id).first()


def _expire_if_stale(db: Session, intent: PaymentIntent) -> None:
    if intent.status != "pending":
        return
    age = utcnow() - (intent.created_at or utcnow())
    if age > timedelta(minutes=INTENT_TTL_MINUTES):
        intent.status = "expired"
        intent.result_desc = "The payment request expired before it was completed."
        db.commit()


def _get_intent(db: Session, reference: str, current_user: User) -> PaymentIntent:
    intent = db.query(PaymentIntent).filter(PaymentIntent.reference == reference).first()
    if not intent:
        raise HTTPException(status_code=404, detail="Payment request not found")
    if current_user.role == "cashier" and intent.cashier_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only view your own payments")
    return intent


def _fail_intent(db: Session, intent: PaymentIntent, description: str) -> None:
    locked = db.query(PaymentIntent).filter(PaymentIntent.id == intent.id).with_for_update().first()
    if not locked or locked.status != "pending":
        db.rollback()
        return
    locked.status = "failed"
    locked.result_desc = description or "Payment was not completed."
    db.commit()


def _settle_intent(db: Session, intent: PaymentIntent, receipt: str | None) -> None:
    """Create the sale only once, after payment is confirmed."""
    locked = (
        db.query(PaymentIntent)
        .filter(PaymentIntent.id == intent.id)
        .with_for_update()
        .first()
    )
    if not locked:
        db.rollback()
        return
    if locked.status == "paid":
        db.rollback()
        return
    if locked.status != "pending":
        db.rollback()
        return

    lines = json.loads(locked.items_json)
    subtotal = sum((Decimal(str(line["total"])) for line in lines), Decimal("0"))
    amount = money(locked.amount)

    try:
        sale = persist_sale(
            db,
            cashier_id=locked.cashier_id,
            lines=lines,
            subtotal=money(subtotal),
            discount=money(locked.discount),
            total=amount,
            vat=vat_component(amount, VAT_RATE),
            payment_method="mpesa",
            customer_name=locked.customer_name,
            client_reference=None,
            sale_time=utcnow(),
            payment_reference=receipt or locked.reference,
        )
        locked.sale_id = sale.id
        locked.status = "paid"
        locked.mpesa_receipt = receipt
        locked.result_desc = "Payment received"
        db.add(AuditEvent(
            actor_id=locked.cashier_id,
            event_type="mpesa.paid",
            details=f"{locked.reference} {amount} receipt={receipt or 'n/a'} sale={sale.sale_number}",
        ))
        db.commit()
    except InsufficientStock as error:
        db.rollback()
        locked = (
            db.query(PaymentIntent)
            .filter(PaymentIntent.id == intent.id)
            .with_for_update()
            .first()
        )
        locked.status = "paid"
        locked.mpesa_receipt = receipt
        locked.problem = f"Payment was received but stock changed: {error}. Refund the customer."
        locked.result_desc = "Payment received — stock unavailable"
        db.add(AuditEvent(
            actor_id=locked.cashier_id,
            event_type="mpesa.paid_without_sale",
            details=f"{locked.reference} {amount} receipt={receipt or 'n/a'} {locked.problem}",
        ))
        db.commit()


def _callback_metadata(callback: dict) -> dict:
    items = (callback.get("CallbackMetadata") or {}).get("Item") or []
    return {
        item.get("Name"): item.get("Value")
        for item in items
        if isinstance(item, dict) and item.get("Name")
    }


def _apply_query_result(db: Session, intent: PaymentIntent, result_code: str, description: str) -> None:
    if result_code == "0":
        _settle_intent(db, intent, intent.mpesa_receipt)
    else:
        _fail_intent(db, intent, description or "Payment was not completed.")


@router.post("/payments/mpesa", dependencies=[Depends(require_roles("owner", "manager", "cashier"))])
def create_mpesa_payment(
    payload: MpesaPaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not (mpesa_configured() or simulation_enabled()):
        raise HTTPException(
            status_code=503,
            detail=(
                "M-Pesa is not configured. Set MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET, "
                "MPESA_PASSKEY and MPESA_SHORTCODE on the API server."
            ),
        )

    try:
        phone = normalise_phone(payload.phone)
        lines, subtotal = price_basket(db, payload.items)
    except MpesaError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except UnknownProduct as error:
        raise HTTPException(status_code=404, detail=str(error))
    except InsufficientStock as error:
        raise HTTPException(status_code=400, detail=str(error))

    discount = money(payload.discount)
    if discount > subtotal:
        raise HTTPException(status_code=400, detail="Discount cannot exceed the subtotal")

    total = money(subtotal - discount)
    if total != total.to_integral_value():
        raise HTTPException(
            status_code=400,
            detail="M-Pesa accepts whole shilling amounts only. Adjust the discount so the total has no cents.",
        )
    if total < 1:
        raise HTTPException(status_code=400, detail="The amount must be at least KSh 1.")

    intent = PaymentIntent(
        reference=f"PAY-{uuid4().hex[:10].upper()}",
        cashier_id=current_user.id,
        method="mpesa",
        status="pending",
        amount=total,
        phone=phone,
        items_json=json.dumps(lines),
        discount=discount,
        customer_name=payload.customer_name,
        result_desc="Awaiting customer approval",
    )
    db.add(intent)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(intent)

    if simulation_enabled():
        intent.result_desc = "Simulation mode: mark this payment paid or failed from the till."
        db.commit()
        return {**_intent_payload(intent), "simulation": True}

    try:
        result = stk_push(
            phone=phone,
            amount=int(total),
            reference=intent.reference,
            description=f"{intent.reference} POS",
        )
    except MpesaError as error:
        intent.status = "failed"
        intent.result_desc = str(error)
        db.commit()
        raise HTTPException(status_code=502, detail=str(error))

    intent.checkout_request_id = result.get("checkout_request_id")
    intent.merchant_request_id = result.get("merchant_request_id")
    intent.result_desc = result.get("customer_message")
    db.commit()

    return {**_intent_payload(intent), "simulation": False}


@router.get("/payments/{reference}")
def get_mpesa_payment(
    reference: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    intent = _get_intent(db, reference, current_user)
    _expire_if_stale(db, intent)
    return _intent_payload(intent, _sale_for(db, intent))


@router.post("/payments/{reference}/verify")
def verify_mpesa_payment(
    reference: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    intent = _get_intent(db, reference, current_user)
    _expire_if_stale(db, intent)
    if intent.status == "paid":
        return _intent_payload(intent, _sale_for(db, intent))
    if intent.status != "pending":
        return _intent_payload(intent, _sale_for(db, intent))
    if simulation_enabled():
        raise HTTPException(
            status_code=400,
            detail="Simulation mode is on. Use the simulate action instead of Safaricom verification.",
        )
    if not intent.checkout_request_id:
        raise HTTPException(status_code=400, detail="This payment never reached Safaricom.")

    try:
        status = query_status(intent.checkout_request_id)
    except MpesaError as error:
        raise HTTPException(status_code=502, detail=str(error))

    _apply_query_result(db, intent, status["result_code"], status["result_desc"])
    db.refresh(intent)
    return _intent_payload(intent, _sale_for(db, intent))


@router.post("/mpesa/callback")
@router.post("/mpesa/callback/{token}")
async def mpesa_callback(
    request: Request,
    token: str | None = None,
    db: Session = Depends(get_db),
):
    """Safaricom's callback. Unauthenticated, so success is always verified by query."""
    if MPESA_CALLBACK_TOKEN and token != MPESA_CALLBACK_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid callback token")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid callback body")

    callback = (body or {}).get("Body", {}).get("stkCallback", {})
    checkout_request_id = callback.get("CheckoutRequestID")
    if not checkout_request_id:
        return _accepted()

    intent = (
        db.query(PaymentIntent)
        .filter(PaymentIntent.checkout_request_id == checkout_request_id)
        .first()
    )
    if not intent or intent.status != "pending":
        return _accepted()

    result_code = str(callback.get("ResultCode"))
    description = callback.get("ResultDesc") or ""

    if result_code != "0":
        _fail_intent(db, intent, description or "Payment was cancelled or failed.")
        return _accepted()

    if simulation_enabled():
        _settle_intent(db, intent, _callback_metadata(callback).get("MpesaReceiptNumber"))
        return _accepted()

    try:
        status = query_status(checkout_request_id)
    except MpesaError:
        # Keep it pending: the till or a later callback can verify it again.
        intent.result_desc = "Payment reported by M-Pesa; awaiting server verification."
        db.commit()
        return _accepted()

    if status["result_code"] == "0":
        _settle_intent(db, intent, _callback_metadata(callback).get("MpesaReceiptNumber"))
    else:
        _fail_intent(db, intent, status["result_desc"] or description)

    return _accepted()


@router.post("/mpesa/simulate/{reference}")
def simulate_mpesa_payment(
    reference: str,
    outcome: str = "paid",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Development-only helper so the full flow can be exercised without Safaricom."""
    if not simulation_enabled():
        raise HTTPException(status_code=404, detail="Not found")

    intent = _get_intent(db, reference, current_user)
    if intent.status == "paid":
        return _intent_payload(intent, _sale_for(db, intent))

    if outcome == "failed":
        _fail_intent(db, intent, "Simulated customer cancellation")
    else:
        _settle_intent(db, intent, f"SIM{intent.reference[-6:]}")

    db.refresh(intent)
    return _intent_payload(intent, _sale_for(db, intent))


@router.get("/mpesa/config")
def mpesa_config():
    return {
        "configured": mpesa_configured(),
        "simulation": simulation_enabled(),
    }
