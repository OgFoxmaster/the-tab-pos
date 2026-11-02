from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import Product


def ensure_demo_products() -> None:
    db: Session = SessionLocal()
    try:
        product_count = db.query(Product).count()
        if product_count > 0:
            return

        demo_products = [
            Product(sku="JAM-001", name="Jameson Irish Whiskey", category="Spirits", unit="bottle", buying_price=2200, selling_price=2450, stock_quantity=25, reorder_level=8),
            Product(sku="KEN-001", name="Kenya Cane", category="Spirits", unit="bottle", buying_price=900, selling_price=1100, stock_quantity=40, reorder_level=12),
            Product(sku="SMI-001", name="Smirnoff Ice", category="Beer", unit="bottle", buying_price=720, selling_price=980, stock_quantity=50, reorder_level=15),
            Product(sku="GUA-001", name="Guinness", category="Beer", unit="bottle", buying_price=1300, selling_price=1650, stock_quantity=30, reorder_level=10),
            Product(sku="WIS-001", name="Tusker Lager", category="Beer", unit="bottle", buying_price=840, selling_price=1050, stock_quantity=35, reorder_level=12),
        ]

        db.add_all(demo_products)
        db.commit()
        print("Seeded demo product catalog")
    finally:
        db.close()
