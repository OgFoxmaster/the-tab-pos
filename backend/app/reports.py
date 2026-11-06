"""Daily, weekly and monthly reporting built from the shared sales records."""

import csv
import io
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session, selectinload

from .config import STORE_CURRENCY, STORE_NAME, VAT_RATE
from .models import Expense, Product, Sale, User

PERIODS = ("daily", "weekly", "monthly")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def resolve_period(period: str, anchor: date | None = None) -> tuple[datetime, datetime, str, str]:
    """Return the UTC window, chart granularity and a human label for a period."""
    anchor_date = anchor or datetime.now(timezone.utc).date()

    if period == "weekly":
        start_date = anchor_date - timedelta(days=anchor_date.weekday())
        end_date = start_date + timedelta(days=7)
        granularity = "day"
        label = f"Week of {start_date.strftime('%d %b %Y')}"
    elif period == "monthly":
        start_date = anchor_date.replace(day=1)
        end_date = (start_date + timedelta(days=32)).replace(day=1)
        granularity = "day"
        label = start_date.strftime("%B %Y")
    else:
        start_date = anchor_date
        end_date = anchor_date + timedelta(days=1)
        granularity = "hour"
        label = start_date.strftime("%d %b %Y")

    start = datetime.combine(start_date, time.min)
    end = datetime.combine(end_date, time.min)
    return start, end, granularity, label


def _decimal(value) -> Decimal:
    return Decimal(str(value or 0))


def _pct_change(current: float, previous: float) -> float | None:
    if previous <= 0:
        return None if current <= 0 else 100.0
    return round(((current - previous) / previous) * 100, 1)


def _summarise(sales: list[Sale]) -> dict:
    paid = [sale for sale in sales if sale.payment_status == "paid"]
    revenue = sum(_decimal(sale.total) for sale in paid)
    discounts = sum(_decimal(sale.discount) for sale in paid)
    cogs = Decimal("0")
    items_sold = 0
    for sale in paid:
        for item in sale.items:
            items_sold += item.quantity
            cogs += _decimal(item.cost_price) * item.quantity
    transactions = len(paid)
    average_basket = (revenue / transactions) if transactions else Decimal("0")
    return {
        "revenue": float(revenue),
        "transactions": transactions,
        "average_basket": round(float(average_basket), 2),
        "items_sold": items_sold,
        "discounts": float(discounts),
        "cogs": float(cogs),
        "gross_profit": round(float(revenue - cogs), 2),
    }


def build_report(db: Session, period: str = "daily", anchor: date | None = None) -> dict:
    if period not in PERIODS:
        period = "daily"

    start, end, granularity, label = resolve_period(period, anchor)
    span = end - start
    previous_start, previous_end = start - span, start

    sales = (
        db.query(Sale)
        .options(selectinload(Sale.items))
        .filter(Sale.sale_time >= start, Sale.sale_time < end)
        .all()
    )
    previous_sales = (
        db.query(Sale)
        .options(selectinload(Sale.items))
        .filter(Sale.sale_time >= previous_start, Sale.sale_time < previous_end)
        .all()
    )
    totals = _summarise(sales)
    previous_totals = _summarise(previous_sales)

    expenses = (
        db.query(Expense)
        .filter(Expense.created_at >= start, Expense.created_at < end)
        .all()
    )
    expense_total = sum(_decimal(expense.amount) for expense in expenses)

    refunded = (
        db.query(Sale)
        .filter(Sale.refunded_at.isnot(None), Sale.refunded_at >= start, Sale.refunded_at < end)
        .all()
    )
    refunded_amount = sum(_decimal(sale.total) for sale in refunded)

    net = _decimal(totals["gross_profit"]) - expense_total

    products = {product.id: product for product in db.query(Product).all()}
    users = {user.id: user for user in db.query(User).all()}

    # Chart series: hourly buckets for a day, per-day buckets for a week or month.
    buckets: list[dict] = []
    if granularity == "hour":
        buckets = [{"label": f"{hour:02d}", "revenue": 0.0, "transactions": 0} for hour in range(24)]
        for sale in sales:
            if sale.payment_status != "paid" or sale.sale_time is None:
                continue
            bucket = buckets[sale.sale_time.hour]
            bucket["revenue"] += float(_decimal(sale.total))
            bucket["transactions"] += 1
    else:
        day_count = (end - start).days
        buckets = [
            {"label": (start + timedelta(days=index)).strftime("%d %b"), "revenue": 0.0, "transactions": 0}
            for index in range(max(day_count, 1))
        ]
        for sale in sales:
            if sale.payment_status != "paid" or sale.sale_time is None:
                continue
            index = (sale.sale_time.date() - start.date()).days
            if 0 <= index < len(buckets):
                buckets[index]["revenue"] += float(_decimal(sale.total))
                buckets[index]["transactions"] += 1
    for bucket in buckets:
        bucket["revenue"] = round(bucket["revenue"], 2)

    top: dict[int, dict] = {}
    payment_mix: dict[str, dict] = {}
    by_cashier: dict[int, dict] = {}
    for sale in sales:
        if sale.payment_status != "paid":
            continue
        method = sale.payment_method or "cash"
        mix = payment_mix.setdefault(method, {"method": method, "amount": 0.0, "count": 0})
        mix["amount"] = round(mix["amount"] + float(_decimal(sale.total)), 2)
        mix["count"] += 1

        cashier = by_cashier.setdefault(
            sale.cashier_id,
            {
                "cashier": users[sale.cashier_id].username if sale.cashier_id in users else "unknown",
                "revenue": 0.0,
                "transactions": 0,
            },
        )
        cashier["revenue"] = round(cashier["revenue"] + float(_decimal(sale.total)), 2)
        cashier["transactions"] += 1

        for item in sale.items:
            product = products.get(item.product_id)
            entry = top.setdefault(
                item.product_id,
                {
                    "name": product.name if product else f"Product {item.product_id}",
                    "sku": product.sku if product else "",
                    "quantity": 0,
                    "revenue": 0.0,
                },
            )
            entry["quantity"] += item.quantity
            entry["revenue"] = round(entry["revenue"] + float(_decimal(item.total)), 2)

    low_stock = [
        {
            "id": product.id,
            "name": product.name,
            "sku": product.sku,
            "stock_quantity": product.stock_quantity,
            "reorder_level": product.reorder_level,
        }
        for product in products.values()
        if product.is_active and (product.stock_quantity or 0) <= (product.reorder_level or 0)
    ]
    low_stock.sort(key=lambda item: item["stock_quantity"])

    vat_included = 0.0
    if VAT_RATE > 0:
        vat_included = round(
            totals["revenue"] - (totals["revenue"] / (1 + VAT_RATE)), 2
        )

    return {
        "store": STORE_NAME,
        "currency": STORE_CURRENCY,
        "period": period,
        "label": label,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "granularity": granularity,
        "totals": {
            **totals,
            "expenses": round(float(expense_total), 2),
            "net": round(float(net), 2),
            "vat_included": vat_included,
            "refunded_amount": round(float(refunded_amount), 2),
            "refunded_count": len(refunded),
            "expense_count": len(expenses),
        },
        "comparison": {
            "previous_revenue": previous_totals["revenue"],
            "previous_transactions": previous_totals["transactions"],
            "revenue_change_pct": _pct_change(totals["revenue"], previous_totals["revenue"]),
            "transactions_change_pct": _pct_change(
                totals["transactions"], previous_totals["transactions"]
            ),
        },
        "series": buckets,
        "top_products": sorted(top.values(), key=lambda item: item["revenue"], reverse=True)[:8],
        "payment_mix": sorted(payment_mix.values(), key=lambda item: item["amount"], reverse=True),
        "by_cashier": sorted(by_cashier.values(), key=lambda item: item["revenue"], reverse=True),
        "low_stock": low_stock[:10],
        "expenses": [
            {
                "description": expense.description,
                "category": expense.category,
                "amount": float(expense.amount),
            }
            for expense in sorted(expenses, key=lambda item: _decimal(item.amount), reverse=True)[:10]
        ],
    }


def report_facts(report: dict) -> dict:
    """Compact, factual payload sent to the AI analyst (never raw rows)."""
    totals = report["totals"]
    return {
        "store": report["store"],
        "currency": report["currency"],
        "period": report["label"],
        "revenue": totals["revenue"],
        "transactions": totals["transactions"],
        "average_basket": totals["average_basket"],
        "items_sold": totals["items_sold"],
        "discounts": totals["discounts"],
        "gross_profit": totals["gross_profit"],
        "expenses": totals["expenses"],
        "net": totals["net"],
        "refunds": {"count": totals["refunded_count"], "amount": totals["refunded_amount"]},
        "revenue_change_pct": report["comparison"]["revenue_change_pct"],
        "top_products": [
            {"name": item["name"], "quantity": item["quantity"], "revenue": item["revenue"]}
            for item in report["top_products"][:5]
        ],
        "payment_mix": [
            {"method": item["method"], "amount": item["amount"]} for item in report["payment_mix"]
        ],
        "low_stock": [
            {"name": item["name"], "stock": item["stock_quantity"], "reorder_level": item["reorder_level"]}
            for item in report["low_stock"][:5]
        ],
    }


def build_briefing(report: dict) -> str:
    """Rules-based summary that works without any AI provider configured."""
    totals = report["totals"]
    comparison = report["comparison"]
    money = report["currency"]
    sentences = [
        f"{report['store']} · {report['label']}: {money} {totals['revenue']:,.0f} from "
        f"{totals['transactions']} sale(s), average basket {money} {totals['average_basket']:,.0f}."
    ]

    change = comparison["revenue_change_pct"]
    if change is None:
        sentences.append("There is no comparable previous period, so no trend is shown.")
    elif change > 0:
        sentences.append(f"Revenue is up {change}% against the previous period.")
    elif change < 0:
        sentences.append(f"Revenue is down {abs(change)}% against the previous period.")
    else:
        sentences.append("Revenue is flat against the previous period.")

    sentences.append(
        f"Gross profit is {money} {totals['gross_profit']:,.0f}, expenses are "
        f"{money} {totals['expenses']:,.0f}, leaving net {money} {totals['net']:,.0f}."
    )

    if report["top_products"]:
        leaders = ", ".join(
            f"{item['name']} ({item['quantity']} sold)" for item in report["top_products"][:3]
        )
        sentences.append(f"Best sellers: {leaders}.")
    else:
        sentences.append("No products were sold in this period.")

    if totals["refunded_count"]:
        sentences.append(
            f"{totals['refunded_count']} refund(s) totalling {money} "
            f"{totals['refunded_amount']:,.0f} were processed."
        )

    if report["low_stock"]:
        names = ", ".join(item["name"] for item in report["low_stock"][:4])
        sentences.append(f"Restock attention: {names}.")
    else:
        sentences.append("No products are at or below their reorder level.")

    return " ".join(sentences)


def report_csv(report: dict) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    totals = report["totals"]

    writer.writerow([f"{report['store']} POS report", report["label"]])
    writer.writerow(["Period", report["period"], "Currency", report["currency"]])
    writer.writerow([])
    writer.writerow(["Metric", "Value"])
    for key in (
        "revenue",
        "transactions",
        "average_basket",
        "items_sold",
        "discounts",
        "cogs",
        "gross_profit",
        "expenses",
        "net",
        "vat_included",
        "refunded_count",
        "refunded_amount",
    ):
        writer.writerow([key.replace("_", " ").title(), totals[key]])

    writer.writerow([])
    writer.writerow(["Top products", "SKU", "Quantity", "Revenue"])
    for item in report["top_products"]:
        writer.writerow([item["name"], item["sku"], item["quantity"], item["revenue"]])

    writer.writerow([])
    writer.writerow(["Payment method", "Amount", "Count"])
    for item in report["payment_mix"]:
        writer.writerow([item["method"], item["amount"], item["count"]])

    writer.writerow([])
    writer.writerow(["Cashier", "Revenue", "Transactions"])
    for item in report["by_cashier"]:
        writer.writerow([item["cashier"], item["revenue"], item["transactions"]])

    writer.writerow([])
    writer.writerow(["Interval", "Revenue", "Transactions"])
    for item in report["series"]:
        writer.writerow([item["label"], item["revenue"], item["transactions"]])

    return buffer.getvalue()
