"""Shared sale pricing and persistence used by cash checkout and M-Pesa settlement."""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from sqlalchemy.orm import Session

from .models import Payment, Product, Sale, SaleItem, StockMovement

MONEY = Decimal("0.01")


class UnknownProduct(Exception):
    def __init__(self, product_id: int):
        self.product_id = product_id
        super().__init__(f"Product {product_id} not found")


class InsufficientStock(Exception):
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Insufficient stock for {name}")


def money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def vat_component(amount: Decimal, rate: float) -> Decimal:
    if rate <= 0:
        return Decimal("0")
    divisor = Decimal("1") + Decimal(str(rate))
    return money(amount - (amount / divisor))


def price_basket(db: Session, items) -> tuple[list[dict], Decimal]:
    """Validate stock, snapshot prices and return priced lines plus the subtotal."""
    quantities: dict[int, int] = {}
    for item in items:
        product_id = getattr(item, "product_id", None)
        if product_id is None and isinstance(item, dict):
            product_id = item["product_id"]
        quantity = getattr(item, "quantity", None)
        if quantity is None and isinstance(item, dict):
            quantity = item["quantity"]
        quantities[int(product_id)] = quantities.get(int(product_id), 0) + int(quantity)

    lines: list[dict] = []
    subtotal = Decimal("0")

    # Sorted order keeps concurrent checkouts acquiring row locks in the same sequence.
    for product_id, quantity in sorted(quantities.items()):
        product = (
            db.query(Product)
            .filter(Product.id == product_id, Product.is_active.is_(True))
            .with_for_update()
            .first()
        )
        if not product:
            raise UnknownProduct(product_id)
        if (product.stock_quantity or 0) < quantity:
            raise InsufficientStock(product.name)

        unit_price = money(product.selling_price)
        cost_price = money(product.buying_price)
        line_total = money(unit_price * quantity)
        subtotal += line_total
        lines.append({
            "product_id": product.id,
            "name": product.name,
            "quantity": quantity,
            "unit_price": str(unit_price),
            "cost_price": str(cost_price),
            "total": str(line_total),
        })

    return lines, money(subtotal)


def persist_sale(
    db: Session,
    *,
    cashier_id: int,
    lines: list[dict],
    subtotal: Decimal,
    discount: Decimal,
    total: Decimal,
    vat: Decimal,
    payment_method: str,
    customer_name: str | None,
    client_reference: str | None,
    sale_time: datetime,
    payment_reference: str | None = None,
) -> Sale:
    """Write the sale, its items, stock movements and payment. The caller commits."""
    sale = Sale(
        sale_number=f"INV-{uuid4().hex[:8].upper()}",
        client_reference=client_reference,
        cashier_id=cashier_id,
        customer_name=customer_name,
        subtotal=subtotal,
        discount=discount,
        vat=vat,
        total=total,
        payment_method=payment_method,
        payment_status="paid",
        sale_time=sale_time,
    )
    db.add(sale)
    db.flush()

    for line in lines:
        product = (
            db.query(Product)
            .filter(Product.id == int(line["product_id"]))
            .with_for_update()
            .first()
        )
        quantity = int(line["quantity"])
        if not product or (product.stock_quantity or 0) < quantity:
            raise InsufficientStock(product.name if product else line.get("name", "a product"))

        product.stock_quantity -= quantity
        db.add(SaleItem(
            sale_id=sale.id,
            product_id=product.id,
            quantity=quantity,
            unit_price=Decimal(str(line["unit_price"])),
            cost_price=Decimal(str(line["cost_price"])) if line.get("cost_price") is not None else None,
            total=Decimal(str(line["total"])),
        ))
        db.add(StockMovement(
            product_id=product.id,
            movement_type="sale",
            quantity=-quantity,
            reference=sale.sale_number,
            notes=f"Sold via {payment_method}",
        ))

    db.add(Payment(
        sale_id=sale.id,
        method=payment_method,
        amount=total,
        reference=payment_reference or sale.sale_number,
        status="completed",
    ))
    return sale
