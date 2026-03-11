"""
models.py - Pydantic request/response models.
These are the data shapes used in API endpoints.
The actual DB schema lives in Supabase (see docs/SETUP.md).
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ─── Enums ────────────────────────────────────────────────────────────────────

class OrderStatus(str, Enum):
    pending = "pending"
    preparing = "preparing"
    ready = "ready"
    completed = "completed"
    cancelled = "cancelled"


class CancellationStatus(str, Enum):
    none = "none"
    requested = "requested"
    approved = "approved"
    rejected = "rejected"


class ModificationStatus(str, Enum):
    none = "none"
    requested = "requested"
    approved = "approved"
    rejected = "rejected"


class BookingStatus(str, Enum):
    confirmed = "confirmed"
    cancelled = "cancelled"
    completed = "completed"


class StaffRole(str, Enum):
    admin = "admin"
    chef = "chef"
    manager = "manager"


# ─── Auth ─────────────────────────────────────────────────────────────────────

class CustomerRegisterRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    pin: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")
    phone: Optional[str] = None
    restaurant_id: Optional[str] = None
    table_number: Optional[str] = None
    allergies: Optional[List[str]] = []


class CustomerLoginRequest(BaseModel):
    name: str
    pin: str = Field(..., min_length=4, max_length=4, pattern=r"^\d{4}$")
    restaurant_id: Optional[str] = None
    table_number: Optional[str] = None


class StaffLoginRequest(BaseModel):
    username: str
    password: str
    restaurant_id: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user_id: str
    name: str
    visit_count: Optional[int] = None
    total_spend: Optional[float] = None
    tags: Optional[List[str]] = []


# ─── Menu ─────────────────────────────────────────────────────────────────────

class MenuItem(BaseModel):
    id: Optional[str] = None
    restaurant_id: str
    name: str
    description: Optional[str] = None
    price: float
    category: str  # Starters | Mains | Drinks | Desserts
    sold_out: bool = False
    allergens: Optional[List[str]] = []


class MenuItemCreate(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    category: str
    sold_out: bool = False
    allergens: Optional[List[str]] = []


class MenuItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    category: Optional[str] = None
    sold_out: Optional[bool] = None
    allergens: Optional[List[str]] = None


# ─── Orders ───────────────────────────────────────────────────────────────────

class OrderItem(BaseModel):
    name: str
    quantity: int
    unit_price: float
    total_price: float


class PlaceOrderRequest(BaseModel):
    natural_language_input: str
    table_number: str
    restaurant_id: Optional[str] = None


class OrderResponse(BaseModel):
    id: str
    restaurant_id: str
    user_id: str
    customer_name: str
    table_number: str
    items: List[OrderItem]
    price: float
    status: OrderStatus
    cancellation_status: CancellationStatus
    modification_status: ModificationStatus
    allergy_warnings: Optional[List[str]] = []
    created_at: datetime


class ModifyOrderRequest(BaseModel):
    modification_text: str  # e.g. "Remove the fries"


class AIOrderParseResponse(BaseModel):
    """What the AI returns after parsing natural language."""
    items: List[OrderItem]
    total: float
    allergy_warnings: List[str] = []
    unrecognized_items: List[str] = []
    sold_out_items: List[str] = []


# ─── Bookings ─────────────────────────────────────────────────────────────────

class CreateBookingRequest(BaseModel):
    party_size: int = Field(..., ge=1, le=20)
    booking_time: str  # ISO string or natural language → parsed server-side
    special_requests: Optional[str] = None
    restaurant_id: Optional[str] = None


class BookingResponse(BaseModel):
    id: str
    restaurant_id: str
    user_id: str
    customer_name: str
    party_size: int
    booking_time: datetime
    status: BookingStatus
    special_requests: Optional[str] = None
    created_at: datetime


# ─── Feedback ─────────────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    order_ratings: Optional[dict] = {}   # {item_name: 1-5}
    overall_rating: int = Field(..., ge=1, le=5)
    comments: Optional[str] = None
    restaurant_id: Optional[str] = None


# ─── CRM / Customer Insights ──────────────────────────────────────────────────

class CustomerInsight(BaseModel):
    id: str
    name: str
    phone: Optional[str] = None
    visit_count: int
    total_spend: float
    tags: List[str]
    last_visit: Optional[datetime] = None
    allergies: Optional[List[str]] = []


# ─── Settings ─────────────────────────────────────────────────────────────────

class RestaurantSettings(BaseModel):
    wifi_password: Optional[str] = None
    opening_hours: Optional[str] = None
    parking_info: Optional[str] = None
    ai_context: Optional[str] = None  # injected into every AI prompt
    table_count: Optional[int] = 20
    max_party_size: Optional[int] = 10


# ─── Staff ────────────────────────────────────────────────────────────────────

class StaffUserCreate(BaseModel):
    username: str
    password: str
    role: StaffRole
    restaurant_id: Optional[str] = None
