from decimal import Decimal
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .bootstrap_owner import ensure_owner
from .config import CORS_ORIGINS
from .db import Base, engine, get_db
from .models import Expense, Payment, Product, Sale, SaleItem, StockMovement, User
from .mpesa import router as mpesa_router
from .seed_data import ensure_demo_products
from .schemas import (
    ExpenseCreate,
    InventoryMovementCreate,
    LoginRequest,
    ProductCreate,
    SaleCreate,
    TokenResponse,
    UserCreate,
    UserOut,
)
from .security import create_access_token, get_current_user, hash_password, require_roles, verify_password

Base.metadata.create_all(bind=engine)
ensure_owner()
ensure_demo_products()

app = FastAPI(title="The Tab POS", version="1.0.0")
app.include_router(mpesa_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "app": "the-tab-pos"}


@app.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not user.is_active or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

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
    return user


@app.get("/users", response_model=list[UserOut], dependencies=[Depends(require_roles("owner", "manager"))])
def list_users(db: Session = Depends(get_db)):
    return db.query(User).all()


@app.get(
    "/products",
    response_model=list[dict],
    dependencies=[Depends(require_roles("owner", "manager", "stock", "cashier"))],
)
def list_products(db: Session = Depends(get_db), q: str | None = Query(default=None)):
    query = db.query(Product)
    if q:
        query = query.filter((Product.name.ilike(f"%{q}%")) | (Product.sku.ilike(f"%{q}%")))
    products = query.order_by(Product.name).all()
    return [{
        "id": p.id,
        "sku": p.sku,
        "name": p.name,
        "category": p.category,
        "unit": p.unit,
        "buying_price": float(p.buying_price),
        "selling_price": float(p.selling_price),
        "stock_quantity": p.stock_quantity,
        "reorder_level": p.reorder_level,
        "is_active": p.is_active,
    } for p in products]


@app.post("/products", response_model=dict, dependencies=[Depends(require_roles("owner", "manager"))])
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    if db.query(Product).filter(Product.sku == payload.sku).first():
        raise HTTPException(status_code=400, detail="SKU already exists")

    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return {"message": "Product created", "product_id": product.id}


@app.post("/sales", response_model=dict, dependencies=[Depends(require_roles("owner", "manager", "cashier"))])
def create_sale(payload: SaleCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    quantities: dict[int, int] = {}
    for item in payload.items:
        quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity

    subtotal = Decimal("0")
    try:
        sale_items = []
        for product_id, quantity in quantities.items():
            product = (
                db.query(Product)
                .filter(Product.id == product_id, Product.is_active.is_(True))
                .with_for_update()
                .first()
            )
            if not product:
                raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
            if product.stock_quantity < quantity:
                raise HTTPException(status_code=400, detail=f"Insufficient stock for {product.name}")

            unit_price = Decimal(str(product.selling_price))
            line_total = unit_price * quantity
            subtotal += line_total
            sale_items.append((product, quantity, unit_price, line_total))

        sale = Sale(
            sale_number=f"INV-{uuid4().hex[:8].upper()}",
            cashier_id=current_user.id,
            subtotal=str(subtotal),
            discount="0",
            total=str(subtotal),
            payment_method=payload.payment_method,
            payment_status="paid",
        )
        db.add(sale)
        db.flush()

        for product, quantity, unit_price, line_total in sale_items:
            product.stock_quantity -= quantity
            db.add(SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                quantity=quantity,
                unit_price=unit_price,
                total=line_total,
            ))
            db.add(StockMovement(
                product_id=product.id,
                movement_type="sale",
                quantity=-quantity,
                reference=sale.sale_number,
                notes=f"Sold via {payload.payment_method}",
            ))

        db.add(Payment(
            sale_id=sale.id,
            method=payload.payment_method,
            amount=str(subtotal),
            reference=sale.sale_number,
            status="completed",
        ))
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {"message": "Sale recorded", "sale_id": sale.id, "sale_number": sale.sale_number, "total": float(subtotal)}


@app.get("/sales", response_model=list[dict])
def list_sales(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("owner", "manager", "cashier")),
):
    query = db.query(Sale)
    if current_user.role == "cashier":
        query = query.filter(Sale.cashier_id == current_user.id)
    sales = query.order_by(Sale.sale_time.desc()).limit(100).all()
    result = []
    for sale in sales:
        result.append({
            "id": sale.id,
            "sale_number": sale.sale_number,
            "cashier_id": sale.cashier_id,
            "subtotal": float(sale.subtotal),
            "discount": float(sale.discount),
            "total": float(sale.total),
            "payment_method": sale.payment_method,
            "payment_status": sale.payment_status,
            "sale_time": sale.sale_time.isoformat() if sale.sale_time else None,
        })
    return result


@app.post("/expenses", response_model=dict, dependencies=[Depends(require_roles("owner", "manager"))])
def create_expense(payload: ExpenseCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
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
    return {"message": "Expense saved", "expense_id": expense.id}


@app.get("/expenses", response_model=list[dict], dependencies=[Depends(require_roles("owner", "manager"))])
def list_expenses(db: Session = Depends(get_db)):
    expenses = db.query(Expense).order_by(Expense.created_at.desc()).all()
    return [{
        "id": e.id,
        "description": e.description,
        "category": e.category,
        "amount": float(e.amount),
        "payment_method": e.payment_method,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    } for e in expenses]


@app.get("/dashboard/summary")
def dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("owner", "manager", "stock", "cashier")),
):
    sales_query = db.query(Sale)
    if current_user.role == "cashier":
        sales_query = sales_query.filter(Sale.cashier_id == current_user.id)
    sales = sales_query.all()
    total_sales = len(sales)
    total_revenue = sum(float(s.total) for s in sales if s.payment_status == "paid")
    total_products = db.query(Product).count()
    low_stock = db.query(Product).filter(Product.stock_quantity <= Product.reorder_level).count()
    return {
        "total_sales": total_sales,
        "total_revenue": total_revenue,
        "total_products": total_products,
        "low_stock": low_stock,
    }


@app.get(
    "/inventory",
    response_model=list[dict],
    dependencies=[Depends(require_roles("owner", "manager", "stock"))],
)
def list_inventory(db: Session = Depends(get_db)):
    products = db.query(Product).filter(Product.is_active.is_(True)).order_by(Product.name).all()
    return [{
        "id": product.id,
        "sku": product.sku,
        "name": product.name,
        "category": product.category,
        "unit": product.unit,
        "buying_price": float(product.buying_price),
        "selling_price": float(product.selling_price),
        "stock_quantity": product.stock_quantity,
        "reorder_level": product.reorder_level,
        "is_active": product.is_active,
    } for product in products]


@app.post(
    "/inventory/movement",
    response_model=dict,
    dependencies=[Depends(require_roles("owner", "manager", "stock"))],
)
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
        movement = StockMovement(
            product_id=product.id,
            movement_type=payload.type,
            quantity=change,
            reference=None,
            notes=payload.note,
        )
        db.add(movement)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "message": "Inventory updated",
        "product_id": product.id,
        "stock_quantity": product.stock_quantity,
    }
