from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .ai_insights import ai_configuration, ask_insight, remaining_questions
from .bootstrap_owner import ensure_owner
from .config import (
    APP_ENV,
    APP_VERSION,
    CORS_ORIGINS,
    OFFLINE_SALE_MAX_AGE_DAYS,
    OFFLINE_SALE_MAX_FUTURE_MINUTES,
    STORE_ADDRESS,
    STORE_CURRENCY,
    STORE_NAME,
    STORE_PHONE,
    STORE_RECEIPT_FOOTER,
    STORE_TAGLINE,
    VAT_RATE,
    assert_production_safety,
)
from .db import Base, engine, get_db
from .migrations import run_migrations
from .accounts import router as accounts_router
from .models import AuditEvent, Expense, Payment, Product, Sale, SaleItem, StockMovement, User
from .mpesa_service import mpesa_configured, simulation_enabled
from .payments import router as payments_router
from .reports import build_briefing, build_report, report_csv
from .sales_service import (
    InsufficientStock,
    UnknownProduct,
    persist_sale,
    price_basket,
    vat_component,
)
from .schemas import (
    ExpenseCreate,
    InsightRequest,
    InventoryMovementCreate,
    LoginRequest,
    ProductCreate,
    ProductUpdate,
    RefundRequest,
    SaleCreate,
    TokenResponse,
    UserCreate,
    UserOut,
    UserUpdate,
    WebSearchRequest,
)
from .security import (
    check_login_allowed,
    clear_login_failures,
    create_access_token,
    get_current_user,
    hash_password,
    note_login_failure,
    require_roles,
    verify_password,
)
from .seed_data import ensure_demo_products
from .web_search import search_web, web_search_configuration

assert_production_safety()
Base.metadata.create_all(bind=engine)
run_migrations()
ensure_owner()
ensure_demo_products()

app = FastAPI(title="The Tab POS", version=APP_VERSION)
app.include_router(accounts_router)
app.include_router(payments_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

MONEY = Decimal("0.01")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _float(value) -> float:
    return float(value or 0)


def _audit(db: Session, actor: User | None, event_type: str, details: str) -> None:
    try:
        db.add(AuditEvent(actor_id=actor.id if actor else None, event_type=event_type, details=details))
        db.commit()
    except Exception:
        db.rollback()


@app.get("/health")
def health(db: Session = Depends(get_db)):
    database_ok = True
    try:
        db.execute(func.coalesce(func.count(User.id), 0).select())
    except Exception:
        database_ok = False
    return {
        "status": "ok" if database_ok else "degraded",
        "app": "the-tab-pos",
        "version": APP_VERSION,
        "environment": APP_ENV,
        "database": "ok" if database_ok else "unavailable",
        "ai_configured": ai_configuration()["configured"],
    }


@app.get("/meta")
def meta():
    """Public store settings the clients need for receipts and formatting."""
    return {
        "store": STORE_NAME,
        "tagline": STORE_TAGLINE,
        "address": STORE_ADDRESS,
        "phone": STORE_PHONE,
        "currency": STORE_CURRENCY,
        "receipt_footer": STORE_RECEIPT_FOOTER,
        "vat_rate": VAT_RATE,
        "version": APP_VERSION,
        "mpesa_enabled": mpesa_configured() or simulation_enabled(),
        "mpesa_simulate": simulation_enabled(),
    }


@app.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    key = data.username.strip().lower()
    check_login_allowed(key)

    user = db.query(User).filter(User.username == data.username.strip()).first()
    if not user or not user.is_active or not verify_password(data.password, user.password_hash):
        note_login_failure(key)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    clear_login_failures(key)
    token = create_access_token(user.username, user.role)
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "username": user.username,
    }


@app.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@app.post("/users", response_model=UserOut, dependencies=[Depends(require_roles("owner", "manager"))])
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == "manager" and payload.role in {"owner", "manager"}:
        raise HTTPException(status_code=403, detail="Managers cannot create owner or manager accounts")

    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already exists")

    user = User(
        username=payload.username,
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    _audit(db, current_user, "user.created", f"{user.username} ({user.role})")
    return user


@app.get("/users", response_model=list[UserOut], dependencies=[Depends(require_roles("owner", "manager"))])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).order_by(User.username).all()


@app.patch("/users/{user_id}", response_model=UserOut, dependencies=[Depends(require_roles("owner", "manager"))])
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Staff account not found")

    if current_user.role == "manager":
        if target.role in {"owner", "manager"} or payload.role in {"owner", "manager"}:
            raise HTTPException(status_code=403, detail="Managers cannot change owner or manager accounts")

    if target.id == current_user.id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")

    if payload.full_name is not None:
        target.full_name = payload.full_name
    if payload.role is not None:
        target.role = payload.role
    if payload.is_active is not None:
        target.is_active = payload.is_active
    if payload.password:
        target.password_hash = hash_password(payload.password)

    db.commit()
    db.refresh(target)
    _audit(db, current_user, "user.updated", f"{target.username} role={target.role} active={target.is_active}")
    return target


def _product_dict(product: Product) -> dict:
    return {
        "id": product.id,
        "sku": product.sku,
        "name": product.name,
        "category": product.category,
        "unit": product.unit,
        "buying_price": _float(product.buying_price),
        "selling_price": _float(product.selling_price),
        "stock_quantity": product.stock_quantity,
        "reorder_level": product.reorder_level,
        "is_active": product.is_active,
    }


@app.get("/products", response_model=list[dict])
def list_products(
    db: Session = Depends(get_db),
    _: User = Depends(require_roles("owner", "manager", "stock", "cashier")),
    q: str | None = Query(default=None, max_length=80),
    include_inactive: bool = Query(default=False),
):
    query = db.query(Product)
    if not include_inactive:
        query = query.filter(Product.is_active.is_(True))
    if q:
        query = query.filter((Product.name.ilike(f"%{q}%")) | (Product.sku.ilike(f"%{q}%")))
    products = query.order_by(Product.name).all()
    return [_product_dict(product) for product in products]


@app.post("/products", response_model=dict, dependencies=[Depends(require_roles("owner", "manager"))])
def create_product(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if db.query(Product).filter(Product.sku == payload.sku).first():
        raise HTTPException(status_code=400, detail="SKU already exists")

    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    _audit(db, current_user, "product.created", f"{product.sku} {product.name}")
    return {"message": "Product created", "product_id": product.id}


@app.patch("/products/{product_id}", response_model=dict, dependencies=[Depends(require_roles("owner", "manager"))])
def update_product(
    product_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    product = db.query(Product).filter(Product.id == product_id).with_for_update().first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)
    _audit(db, current_user, "product.updated", f"{product.sku} {product.name}")
    return {"message": "Product updated", "product": _product_dict(product)}


def _resolve_sale_time(sold_at: datetime | None) -> datetime:
    now = utcnow()
    if sold_at is None:
        return now

    value = sold_at
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)

    if value > now + timedelta(minutes=OFFLINE_SALE_MAX_FUTURE_MINUTES):
        raise HTTPException(status_code=400, detail="The sale time cannot be in the future")
    if value < now - timedelta(days=OFFLINE_SALE_MAX_AGE_DAYS):
        raise HTTPException(
            status_code=400,
            detail=f"Offline sales older than {OFFLINE_SALE_MAX_AGE_DAYS} days cannot be synced",
        )
    return value


def _sale_payload(sale: Sale, duplicate: bool = False) -> dict:
    return {
        "message": "Sale already recorded" if duplicate else "Sale recorded",
        "duplicate": duplicate,
        "sale_id": sale.id,
        "sale_number": sale.sale_number,
        "subtotal": _float(sale.subtotal),
        "discount": _float(sale.discount),
        "vat": _float(sale.vat),
        "total": _float(sale.total),
        "payment_method": sale.payment_method,
        "payment_status": sale.payment_status,
        "sale_time": sale.sale_time.isoformat() if sale.sale_time else None,
    }


@app.post("/sales", response_model=dict, dependencies=[Depends(require_roles("owner", "manager", "cashier"))])
def create_sale(
    payload: SaleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Offline replays must be safe: the same client reference always returns one sale.
    if payload.client_reference:
        existing = db.query(Sale).filter(Sale.client_reference == payload.client_reference).first()
        if existing:
            return _sale_payload(existing, duplicate=True)

    try:
        lines, subtotal = price_basket(db, payload.items)
    except UnknownProduct as error:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(error))
    except InsufficientStock as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error))

    discount = _money(Decimal(str(payload.discount or 0)))
    if discount > subtotal:
        db.rollback()
        raise HTTPException(status_code=400, detail="Discount cannot exceed the subtotal")

    total = _money(subtotal - discount)
    vat = vat_component(total, VAT_RATE)
    sale_time = _resolve_sale_time(payload.sold_at)

    try:
        sale = persist_sale(
            db,
            cashier_id=current_user.id,
            lines=lines,
            subtotal=subtotal,
            discount=discount,
            total=total,
            vat=vat,
            payment_method=payload.payment_method,
            customer_name=payload.customer_name,
            client_reference=payload.client_reference,
            sale_time=sale_time,
        )
        db.commit()
    except InsufficientStock as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error))
    except IntegrityError:
        db.rollback()
        if payload.client_reference:
            existing = db.query(Sale).filter(Sale.client_reference == payload.client_reference).first()
            if existing:
                return _sale_payload(existing, duplicate=True)
        raise HTTPException(status_code=409, detail="The sale could not be saved. Please retry.")
    except Exception:
        db.rollback()
        raise

    _audit(db, current_user, "sale.created", f"{sale.sale_number} total {total} ({payload.payment_method})")
    return _sale_payload(sale)


@app.get("/sales", response_model=list[dict])
def list_sales(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("owner", "manager", "cashier")),
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    q: str | None = Query(default=None, max_length=80),
    payment_status: str | None = Query(default=None, alias="status", max_length=20),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100000),
):
    query = db.query(Sale, User.username).join(User, User.id == Sale.cashier_id)

    if current_user.role == "cashier":
        query = query.filter(Sale.cashier_id == current_user.id)
    if start:
        query = query.filter(Sale.sale_time >= datetime.combine(start, time.min))
    if end:
        query = query.filter(Sale.sale_time < datetime.combine(end + timedelta(days=1), time.min))
    if q:
        query = query.filter(Sale.sale_number.ilike(f"%{q}%"))
    if payment_status in {"paid", "refunded"}:
        query = query.filter(Sale.payment_status == payment_status)

    rows = query.order_by(Sale.sale_time.desc()).offset(offset).limit(limit).all()
    return [
        {
            "id": sale.id,
            "sale_number": sale.sale_number,
            "cashier_id": sale.cashier_id,
            "cashier": username,
            "customer_name": sale.customer_name,
            "subtotal": _float(sale.subtotal),
            "discount": _float(sale.discount),
            "vat": _float(sale.vat),
            "total": _float(sale.total),
            "payment_method": sale.payment_method,
            "payment_status": sale.payment_status,
            "sale_time": sale.sale_time.isoformat() if sale.sale_time else None,
            "refunded_at": sale.refunded_at.isoformat() if sale.refunded_at else None,
            "offline": bool(sale.client_reference),
        }
        for sale, username in rows
    ]


@app.get("/sales/{sale_id}", dependencies=[Depends(require_roles("owner", "manager", "cashier"))])
def get_sale(
    sale_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sale = (
        db.query(Sale)
        .options(selectinload(Sale.items))
        .filter(Sale.id == sale_id)
        .first()
    )
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    if current_user.role == "cashier" and sale.cashier_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only view your own sales")

    product_ids = [item.product_id for item in sale.items]
    products = {
        product.id: product
        for product in db.query(Product).filter(Product.id.in_(product_ids)).all()
    } if product_ids else {}

    return {
        **_sale_payload(sale),
        "cashier_id": sale.cashier_id,
        "customer_name": sale.customer_name,
        "refunded_at": sale.refunded_at.isoformat() if sale.refunded_at else None,
        "items": [
            {
                "product_id": item.product_id,
                "name": products[item.product_id].name if item.product_id in products else "Product",
                "sku": products[item.product_id].sku if item.product_id in products else "",
                "quantity": item.quantity,
                "unit_price": _float(item.unit_price),
                "total": _float(item.total),
            }
            for item in sale.items
        ],
    }


@app.post("/sales/{sale_id}/refund", response_model=dict, dependencies=[Depends(require_roles("owner", "manager"))])
def refund_sale(
    sale_id: int,
    payload: RefundRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sale = db.query(Sale).filter(Sale.id == sale_id).with_for_update().first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    if sale.payment_status == "refunded":
        raise HTTPException(status_code=400, detail="This sale has already been refunded")

    items = db.query(SaleItem).filter(SaleItem.sale_id == sale.id).all()
    try:
        for item in items:
            product = db.query(Product).filter(Product.id == item.product_id).with_for_update().first()
            if product:
                product.stock_quantity += item.quantity
            db.add(StockMovement(
                product_id=item.product_id,
                movement_type="refund",
                quantity=item.quantity,
                reference=sale.sale_number,
                notes=payload.reason or "Sale refunded",
            ))

        db.query(Payment).filter(Payment.sale_id == sale.id).update({"status": "refunded"})
        sale.payment_status = "refunded"
        sale.refunded_at = utcnow()
        sale.refunded_by = current_user.id
        db.commit()
    except Exception:
        db.rollback()
        raise

    _audit(
        db,
        current_user,
        "sale.refunded",
        f"{sale.sale_number} total {_float(sale.total)} reason={payload.reason or 'n/a'}",
    )
    return {
        "message": "Sale refunded and stock restored",
        "sale_number": sale.sale_number,
        "total": _float(sale.total),
        "restored_items": len(items),
    }


@app.post("/expenses", response_model=dict, dependencies=[Depends(require_roles("owner", "manager"))])
def create_expense(
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    expense = Expense(
        description=payload.description,
        category=payload.category,
        amount=str(payload.amount),
        payment_method=payload.payment_method,
        recorded_by=current_user.id,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    _audit(db, current_user, "expense.created", f"{expense.description} {payload.amount}")
    return {"message": "Expense saved", "expense_id": expense.id}


@app.get("/expenses", response_model=list[dict], dependencies=[Depends(require_roles("owner", "manager"))])
def list_expenses(db: Session = Depends(get_db)):
    expenses = db.query(Expense).order_by(Expense.created_at.desc()).all()
    return [{
        "id": expense.id,
        "description": expense.description,
        "category": expense.category,
        "amount": _float(expense.amount),
        "payment_method": expense.payment_method,
        "created_at": expense.created_at.isoformat() if expense.created_at else None,
    } for expense in expenses]


@app.get("/dashboard/summary")
def dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("owner", "manager", "stock", "cashier")),
):
    paid = db.query(Sale).filter(Sale.payment_status == "paid")
    if current_user.role == "cashier":
        paid = paid.filter(Sale.cashier_id == current_user.id)

    total_sales = paid.count()
    total_revenue = _float(
        db.query(func.coalesce(func.sum(Sale.total), 0))
        .filter(Sale.payment_status == "paid")
        .filter(Sale.cashier_id == current_user.id if current_user.role == "cashier" else True)
        .scalar()
    )

    today_start = datetime.combine(utcnow().date(), time.min)
    today_revenue = _float(
        db.query(func.coalesce(func.sum(Sale.total), 0))
        .filter(Sale.payment_status == "paid", Sale.sale_time >= today_start)
        .filter(Sale.cashier_id == current_user.id if current_user.role == "cashier" else True)
        .scalar()
    )
    today_transactions = (
        db.query(Sale)
        .filter(Sale.payment_status == "paid", Sale.sale_time >= today_start)
        .filter(Sale.cashier_id == current_user.id if current_user.role == "cashier" else True)
        .count()
    )

    total_products = db.query(Product).filter(Product.is_active.is_(True)).count()
    low_stock = (
        db.query(Product)
        .filter(Product.is_active.is_(True), Product.stock_quantity <= Product.reorder_level)
        .count()
    )
    return {
        "total_sales": total_sales,
        "total_revenue": total_revenue,
        "today_revenue": today_revenue,
        "today_transactions": today_transactions,
        "total_products": total_products,
        "low_stock": low_stock,
    }


@app.get("/inventory", response_model=list[dict], dependencies=[Depends(require_roles("owner", "manager", "stock"))])
def list_inventory(
    db: Session = Depends(get_db),
    include_inactive: bool = Query(default=False),
):
    query = db.query(Product)
    if not include_inactive:
        query = query.filter(Product.is_active.is_(True))
    products = query.order_by(Product.name).all()
    return [_product_dict(product) for product in products]


@app.post("/inventory/movement", response_model=dict, dependencies=[Depends(require_roles("owner", "manager", "stock"))])
def record_inventory_movement(
    payload: InventoryMovementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    product = (
        db.query(Product)
        .filter(Product.id == payload.product_id, Product.is_active.is_(True))
        .with_for_update()
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    change = -payload.quantity if payload.type == "adjust_remove" else payload.quantity
    if product.stock_quantity + change < 0:
        raise HTTPException(status_code=400, detail=f"Insufficient stock for {product.name}")

    try:
        product.stock_quantity += change
        db.add(StockMovement(
            product_id=product.id,
            movement_type=payload.type,
            quantity=change,
            reference=None,
            notes=payload.note,
        ))
        db.commit()
    except Exception:
        db.rollback()
        raise

    _audit(db, current_user, "inventory.movement", f"{product.sku} {change:+d} ({payload.type})")
    return {
        "message": "Inventory updated",
        "product_id": product.id,
        "stock_quantity": product.stock_quantity,
    }


@app.get("/reports/summary", dependencies=[Depends(require_roles("owner", "manager"))])
def reports_summary(
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly)$"),
    anchor: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return build_report(db, period, anchor)


@app.get("/reports/export.csv", dependencies=[Depends(require_roles("owner", "manager"))])
def reports_export(
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly)$"),
    anchor: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    report = build_report(db, period, anchor)
    filename = f"the-tab-{report['period']}-{report['start'][:10]}.csv"
    return Response(
        content=report_csv(report),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/ai/status")
def ai_status_endpoint(current_user: User = Depends(get_current_user)):
    return {**ai_configuration(), "remaining_today": remaining_questions(current_user.username)}


@app.get("/ai/briefing", dependencies=[Depends(require_roles("owner", "manager"))])
def ai_briefing(
    period: str = Query(default="daily", pattern="^(daily|weekly|monthly)$"),
    anchor: date | None = Query(default=None),
    db: Session = Depends(get_db),
):
    report = build_report(db, period, anchor)
    return {
        "briefing": build_briefing(report),
        "label": report["label"],
        "period": report["period"],
        "totals": report["totals"],
        "top_products": report["top_products"][:5],
    }


@app.post("/ai/insights", dependencies=[Depends(require_roles("owner", "manager"))])
def ai_insights(
    payload: InsightRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    anchor = None
    if payload.anchor:
        try:
            anchor = date.fromisoformat(payload.anchor)
        except ValueError:
            raise HTTPException(status_code=400, detail="anchor must be a YYYY-MM-DD date")

    report = build_report(db, payload.period, anchor)
    return ask_insight(report, payload.question, current_user.username)


@app.get("/ai/web-search/status")
def web_search_status_endpoint(current_user: User = Depends(get_current_user)):
    return web_search_configuration()


@app.post("/ai/web-search", dependencies=[Depends(require_roles("owner", "manager"))])
def web_search_endpoint(payload: WebSearchRequest):
    return search_web(payload.query, payload.num_results)
