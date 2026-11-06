from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=80)
    email: str = Field(..., min_length=3, max_length=120)
    full_name: str = Field(..., min_length=1, max_length=150)
    password: str = Field(..., min_length=8, max_length=200)
    role: Literal["owner", "manager", "cashier", "stock"] = "cashier"


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    role: Optional[Literal["owner", "manager", "cashier", "stock"]] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=200)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    full_name: str
    role: str
    is_active: bool


class ProductCreate(BaseModel):
    sku: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=150)
    category: str = "General"
    unit: str = "unit"
    buying_price: float = Field(default=0, ge=0)
    selling_price: float = Field(default=0, ge=0)
    stock_quantity: int = Field(default=0, ge=0)
    reorder_level: int = Field(default=10, ge=0)


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    category: Optional[str] = Field(default=None, max_length=100)
    unit: Optional[str] = Field(default=None, max_length=30)
    buying_price: Optional[float] = Field(default=None, ge=0)
    selling_price: Optional[float] = Field(default=None, ge=0)
    reorder_level: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sku: str
    name: str
    category: str
    unit: str
    buying_price: float
    selling_price: float
    stock_quantity: int
    reorder_level: int
    is_active: bool


class InventoryMovementCreate(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, le=100000)
    type: Literal["receive", "adjust_add", "adjust_remove"]
    note: str | None = Field(default=None, max_length=500)


class SaleItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(gt=0, le=10000)


class SaleCreate(BaseModel):
    payment_method: Literal["cash"] = "cash"
    items: list[SaleItemCreate] = Field(min_length=1, max_length=200)
    discount: float = Field(default=0, ge=0)
    customer_name: str | None = Field(default=None, max_length=120)
    # Offline queue support: a till-generated UUID plus the time the sale happened.
    client_reference: str | None = Field(default=None, min_length=8, max_length=64)
    sold_at: datetime | None = None


class RefundRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class SaleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sale_number: str
    cashier_id: int
    subtotal: float
    discount: float
    total: float
    payment_method: str
    payment_status: str


class ExpenseCreate(BaseModel):
    description: str = Field(..., min_length=1, max_length=200)
    category: str = Field(default="General", max_length=80)
    amount: float = Field(gt=0)
    payment_method: str = Field(default="cash", max_length=40)


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    description: str
    category: str
    amount: float
    payment_method: str


class InsightRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)
    period: Literal["daily", "weekly", "monthly"] = "daily"
    anchor: Optional[str] = Field(default=None, max_length=10)


class MpesaPaymentCreate(BaseModel):
    items: list[SaleItemCreate] = Field(min_length=1, max_length=200)
    phone: str = Field(..., min_length=9, max_length=20)
    discount: float = Field(default=0, ge=0)
    customer_name: str | None = Field(default=None, max_length=120)


class OwnerRegister(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=200)
    signup_code: str | None = Field(default=None, max_length=200)


class ForgotPassword(BaseModel):
    email: EmailStr


class ResetPassword(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)
    password: str = Field(..., min_length=8, max_length=200)


class ChangePassword(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=200)
    new_password: str = Field(..., min_length=8, max_length=200)


class WebSearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=300)
    num_results: Optional[int] = Field(default=None, ge=1, le=10)
