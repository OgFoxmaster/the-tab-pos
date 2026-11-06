from sqlalchemy.orm import Session

from .config import SEED_DEMO_DATA
from .db import SessionLocal
from .models import Product


def ensure_demo_products() -> None:
    if not SEED_DEMO_DATA:
        return

    db: Session = SessionLocal()
    try:
        if db.query(Product).count() > 0:
            return

        demo_products = [
            Product(sku="JAM-001", name="Jameson Irish Whiskey", category="Spirits", unit="bottle", buying_price=2200, selling_price=2450, stock_quantity=25, reorder_level=8),
            Product(sku="KEN-001", name="Kenya Cane", category="Spirits", unit="bottle", buying_price=900, selling_price=1100, stock_quantity=40, reorder_level=12),
            Product(sku="SMI-001", name="Smirnoff Ice", category="Beer", unit="bottle", buying_price=720, selling_price=980, stock_quantity=50, reorder_level=15),
            Product(sku="GUA-001", name="Guinness", category="Beer", unit="bottle", buying_price=1300, selling_price=1650, stock_quantity=30, reorder_level=10),
            Product(sku="TUS-001", name="Tusker Lager", category="Beer", unit="bottle", buying_price=840, selling_price=1050, stock_quantity=35, reorder_level=12),
            Product(sku="GIL-001", name="Gilbey's Gin", category="Spirits", unit="bottle", buying_price=1350, selling_price=1600, stock_quantity=18, reorder_level=8),
            Product(sku="BAC-001", name="Bacardi Carta Blanca", category="Spirits", unit="bottle", buying_price=2500, selling_price=2900, stock_quantity=12, reorder_level=6),
            Product(sku="FOU-001", name="Four Cousins Sweet Red", category="Wine", unit="bottle", buying_price=1100, selling_price=1350, stock_quantity=22, reorder_level=8),
            Product(sku="ROB-001", name="Robertson Sauvignon Blanc", category="Wine", unit="bottle", buying_price=1450, selling_price=1750, stock_quantity=9, reorder_level=6),
            Product(sku="COK-001", name="Coke 500ml", category="Soft drinks", unit="bottle", buying_price=50, selling_price=80, stock_quantity=120, reorder_level=30),
            Product(sku="WAT-001", name="Mineral Water 1L", category="Soft drinks", unit="bottle", buying_price=40, selling_price=70, stock_quantity=90, reorder_level=24),
            Product(sku="ICE-001", name="Ice Pack 2kg", category="Essentials", unit="pack", buying_price=120, selling_price=200, stock_quantity=40, reorder_level=10),
        ]

        db.add_all(demo_products)
        db.commit()
        print("Seeded demo product catalog")
    finally:
        db.close()
