from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(150), nullable=False)
    role = Column(String(40), nullable=False, default="cashier")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    sales = relationship("Sale", back_populates="cashier")
    audit_events = relationship("AuditEvent", back_populates="actor")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(150), nullable=False, index=True)
    category = Column(String(100), default="General")
    unit = Column(String(30), default="unit")
    buying_price = Column(Numeric(10, 2), nullable=False, default=0)
    selling_price = Column(Numeric(10, 2), nullable=False, default=0)
    stock_quantity = Column(Integer, default=0)
    reorder_level = Column(Integer, default=10)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    sale_items = relationship("SaleItem", back_populates="product")
    movements = relationship("StockMovement", back_populates="product")


class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    phone = Column(String(30), nullable=True)
    email = Column(String(120), nullable=True)
    address = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    movement_type = Column(String(50), nullable=False)
    quantity = Column(Integer, nullable=False)
    reference = Column(String(80), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="movements")


class Sale(Base):
    __tablename__ = "sales"

    id = Column(Integer, primary_key=True, index=True)
    sale_number = Column(String(50), unique=True, index=True, nullable=False)
    cashier_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    subtotal = Column(Numeric(12, 2), default=0)
    discount = Column(Numeric(12, 2), default=0)
    total = Column(Numeric(12, 2), default=0)
    payment_method = Column(String(40), default="cash")
    payment_status = Column(String(40), default="paid")
    sale_time = Column(DateTime, default=datetime.utcnow)

    cashier = relationship("User", back_populates="sales")
    items = relationship("SaleItem", back_populates="sale")
    payments = relationship("Payment", back_populates="sale")


class SaleItem(Base):
    __tablename__ = "sale_items"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    total = Column(Numeric(10, 2), nullable=False)

    sale = relationship("Sale", back_populates="items")
    product = relationship("Product", back_populates="sale_items")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("sales.id"), nullable=False)
    method = Column(String(40), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    reference = Column(String(120), nullable=True)
    status = Column(String(40), default="completed")
    paid_at = Column(DateTime, default=datetime.utcnow)

    sale = relationship("Sale", back_populates="payments")


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    description = Column(String(200), nullable=False)
    category = Column(String(80), default="General")
    amount = Column(Numeric(12, 2), nullable=False)
    payment_method = Column(String(40), default="cash")
    recorded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    event_type = Column(String(80), nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    actor = relationship("User", back_populates="audit_events")
