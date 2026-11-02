from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


class UserCreate(BaseModel):
    username: str
    email: str
    full_name: str
    password: str = Field(..., min_length=6)
    role: Literal["owner", "manager", "cashier", "stock"] = "cashier"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    full_name: str
    role: str
    is_active: bool


class ProductCreate(BaseModel):
    sku: str
    name: str
    category: str = "General"
    unit: str = "unit"
    buying_price: float = Field(default=0, ge=0)
    selling_price: float = Field(default=0, ge=0)
    stock_quantity: int = Field(default=0, ge=0)
    reorder_level: int = Field(default=10, ge=0)


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
    quantity: int = Field(gt=0)
    type: Literal["receive", "adjust_add", "adjust_remove"]
    note: str | None = None


class SaleItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)


class SaleCreate(BaseModel):
    payment_method: Literal["cash"] = "cash"
    items: list[SaleItemCreate] = Field(min_length=1)


class PaymentCreate(BaseModel):
    method: str
    amount: float
    reference: Optional[str] = None


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
    description: str
    category: str = "General"
    amount: float = Field(gt=0)
    payment_method: str = "cash"


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    description: str
    category: str
    amount: float
    payment_method: str
