from datetime import datetime, date
from typing import Optional, List

from pydantic import BaseModel, Field, field_validator

from app.models import UserRole, ServiceCategory, BookingStatus, ShiftType


def normalize_phone(v: str) -> str:
    digits = "".join(ch for ch in v if ch.isdigit() or ch == "+")
    if len(digits.lstrip("+")) < 10:
        raise ValueError("Некорректный номер телефона")
    return digits


# ---------- Auth ----------

class OTPRequest(BaseModel):
    phone: str = Field(..., examples=["+79991234567"])

    @field_validator("phone")
    @classmethod
    def _norm(cls, v: str) -> str:
        return normalize_phone(v)


class OTPVerify(BaseModel):
    phone: str
    code: str
    full_name: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def _norm(cls, v: str) -> str:
        return normalize_phone(v)


class StaffLogin(BaseModel):
    login: str = Field(..., description="Логин (username) или телефон")
    password: str


class SetPassword(BaseModel):
    username: str = Field(..., min_length=3, max_length=60)
    password: str = Field(..., min_length=4)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole


class UserOut(BaseModel):
    id: int
    phone: Optional[str]
    full_name: Optional[str]
    role: UserRole
    punch_count: int          # сколько ананасов на текущей карте (0-11)
    total_full_washes: int    # всего полных моек за всё время

    class Config:
        from_attributes = True


# ---------- Services ----------

class ServiceOut(BaseModel):
    id: int
    category: ServiceCategory
    name: str
    description: Optional[str]
    price_from: float
    duration_min: Optional[int]
    counts_towards_loyalty: bool

    class Config:
        from_attributes = True


class ServiceCreate(BaseModel):
    category: ServiceCategory
    name: str
    description: Optional[str] = None
    price_from: float
    duration_min: Optional[int] = None
    sort_order: int = 0
    counts_towards_loyalty: bool = False


# ---------- Bookings ----------

class BookingCreate(BaseModel):
    service_id: int
    scheduled_at: datetime
    comment: Optional[str] = None


class BookingOut(BaseModel):
    id: int
    service_id: int
    employee_id: Optional[int]
    scheduled_at: datetime
    status: BookingStatus
    box_number: Optional[int]
    price: Optional[float]
    discount_pct: int
    comment: Optional[str]

    class Config:
        from_attributes = True


class BookingUpdate(BaseModel):
    status: Optional[BookingStatus] = None
    employee_id: Optional[int] = None
    box_number: Optional[int] = None
    price: Optional[float] = None


# ---------- Walk-in заказы (журнал без предварительной записи) ----------

class WalkInOrderCreate(BaseModel):
    order_date: date
    service_name_raw: str
    service_id: Optional[int] = None
    extra_service: Optional[str] = None
    car_model: Optional[str] = None
    amount: float
    contact_name: Optional[str] = None
    client_phone: Optional[str] = None  # если указать — попробуем привязать/создать клиента и начислить ананас
    employee_id: Optional[int] = None
    time_note: Optional[str] = None


class WalkInOrderOut(BaseModel):
    id: int
    order_date: date
    time_note: Optional[str]
    service_id: Optional[int]
    service_name_raw: str
    extra_service: Optional[str]
    car_model: Optional[str]
    amount: float
    contact_name: Optional[str]
    employee_id: Optional[int]

    class Config:
        from_attributes = True


# ---------- Dry cleaning ----------

class DryCleaningOrderCreate(BaseModel):
    order_date: date
    car_model: str
    works_description: str
    phone: Optional[str] = None
    amount: float
    employee_payout: Optional[float] = None
    employee_id: Optional[int] = None


class DryCleaningOrderOut(BaseModel):
    id: int
    order_date: date
    car_model: str
    works_description: str
    phone: Optional[str]
    amount: float
    employee_payout: Optional[float]
    status: BookingStatus
    photos_before: List[str] = []
    photos_after: List[str] = []

    class Config:
        from_attributes = True


# ---------- Schedule ----------

class EmployeeOut(BaseModel):
    id: int
    full_name: str
    position: str
    color_tag: str

    class Config:
        from_attributes = True


class EmployeeCreate(BaseModel):
    full_name: str
    position: str = "Мойщик"
    color_tag: str = "#00C2CB"


class ShiftSet(BaseModel):
    employee_id: int
    work_date: date
    shift_type: ShiftType
    note: Optional[str] = None


class ShiftOut(BaseModel):
    id: int
    employee_id: int
    work_date: date
    shift_type: ShiftType
    note: Optional[str]

    class Config:
        from_attributes = True


# ---------- 2GIS ----------

class GisSettingsOut(BaseModel):
    org_id: Optional[str]
    org_url: Optional[str]
    rating: Optional[float]
    reviews_count: Optional[int]
    last_synced_at: Optional[datetime]

    class Config:
        from_attributes = True


class GisSettingsUpdate(BaseModel):
    org_id: Optional[str] = None
    org_url: Optional[str] = None
    api_key: Optional[str] = None


class GisReviewOut(BaseModel):
    author_name: Optional[str]
    rating: Optional[int]
    text: Optional[str]
    published_at: Optional[datetime]

    class Config:
        from_attributes = True


# ---------- Admin stats ----------

class StatsSummary(BaseModel):
    period_from: date
    period_to: date
    wash_bookings_count: int
    wash_revenue: float
    dry_cleaning_orders_count: int
    dry_cleaning_revenue: float
    dry_cleaning_payouts: float
