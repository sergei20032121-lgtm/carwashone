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
    referral_code: Optional[str] = None

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
    birthday: Optional[date] = None
    referral_code: Optional[str] = None
    tenure_label: str = ""

    class Config:
        from_attributes = True


class BirthdayUpdate(BaseModel):
    birthday: date


# ---------- Services ----------

class ServiceOut(BaseModel):
    id: int
    category: ServiceCategory
    name: str
    description: Optional[str]
    price_from: float
    price_to: Optional[float] = None
    duration_min: Optional[int]
    counts_towards_loyalty: bool
    payout_pct: float = 0

    class Config:
        from_attributes = True


class ServiceCreate(BaseModel):
    category: ServiceCategory
    name: str
    description: Optional[str] = None
    price_from: float
    price_to: Optional[float] = None
    duration_min: Optional[int] = None
    sort_order: int = 0
    counts_towards_loyalty: bool = False
    payout_pct: float = 35


# ---------- Bookings ----------

class BookingCreate(BaseModel):
    service_id: int
    scheduled_at: datetime
    comment: Optional[str] = None
    car_profile_id: Optional[int] = None


class BookingOut(BaseModel):
    id: int
    service_id: int
    employee_id: Optional[int]
    scheduled_at: datetime
    status: BookingStatus
    box_number: Optional[int]
    price: Optional[float]
    discount_pct: int
    employee_payout: Optional[float] = None
    comment: Optional[str]
    rating: Optional[int] = None
    rating_comment: Optional[str] = None
    client_name: str = "Клиент"
    client_phone: Optional[str] = None
    service_name: str = "Услуга"
    service_duration_min: Optional[int] = None

    class Config:
        from_attributes = True


class BookingUpdate(BaseModel):
    status: Optional[BookingStatus] = None
    employee_id: Optional[int] = None
    box_number: Optional[int] = None
    price: Optional[float] = None


class RatingSubmit(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None


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
    assigned_employee_names: List[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class WalkInOrderUpdate(BaseModel):
    order_date: Optional[date] = None
    service_name_raw: Optional[str] = None
    service_id: Optional[int] = None
    extra_service: Optional[str] = None
    car_model: Optional[str] = None
    amount: Optional[float] = None
    contact_name: Optional[str] = None
    employee_id: Optional[int] = None
    time_note: Optional[str] = None


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
    assigned_employee_names: List[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class DryCleaningOrderUpdate(BaseModel):
    order_date: Optional[date] = None
    car_model: Optional[str] = None
    works_description: Optional[str] = None
    phone: Optional[str] = None
    amount: Optional[float] = None
    employee_payout: Optional[float] = None
    employee_id: Optional[int] = None


# ---------- Schedule ----------

class EmployeeOut(BaseModel):
    id: int
    full_name: str
    position: str
    color_tag: str
    is_admin_role: bool = False
    is_active: bool = True

    class Config:
        from_attributes = True


class EmployeeCreate(BaseModel):
    full_name: str
    position: str = "Мойщик"
    color_tag: str = "#00C2CB"
    is_admin_role: bool = False


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


# ---------- Публичная витрина (реальная активность, загруженность) ----------

class RecentActivityItem(BaseModel):
    name: str
    service_label: str
    when: datetime


class BusyHourItem(BaseModel):
    hour: int
    load_pct: int


class BusyHoursOut(BaseModel):
    hours: List[BusyHourItem]
    has_data: bool


class CurrentLoadOut(BaseModel):
    active_count: int
    capacity: int
    level: str  # low | medium | high


# ---------- VK ----------

class VkSettingsOut(BaseModel):
    group_domain: Optional[str]
    last_synced_at: Optional[datetime]

    class Config:
        from_attributes = True


class VkSettingsUpdate(BaseModel):
    group_domain: Optional[str] = None
    access_token: Optional[str] = None


class VkPostOut(BaseModel):
    vk_post_id: int
    text: Optional[str]
    photo_urls: List[str] = []
    likes: int
    published_at: Optional[datetime]
    is_pinned: bool

    class Config:
        from_attributes = True


# ---------- Профили машин клиента ----------

class CarProfileCreate(BaseModel):
    brand: str
    plate: Optional[str] = None
    nickname: Optional[str] = None


class CarProfileOut(BaseModel):
    id: int
    brand: str
    plate: Optional[str]
    nickname: Optional[str]

    class Config:
        from_attributes = True


# ---------- Реферальная программа ----------

class ReferralInfo(BaseModel):
    referral_code: str
    referred_count: int
    referral_link: str


# ---------- Подарочные сертификаты ----------

class GiftCertificateCreate(BaseModel):
    amount: float = Field(..., gt=0)
    issued_to_phone: Optional[str] = None


class GiftCertificateOut(BaseModel):
    code: str
    amount: float
    issued_to_phone: Optional[str]
    is_used: bool
    created_at: datetime

    class Config:
        from_attributes = True


class GiftCertificateRedeem(BaseModel):
    code: str


# ---------- Аудит-лог ----------

class AuditLogOut(BaseModel):
    id: int
    action: str
    entity: str
    entity_id: Optional[int]
    note: Optional[str]
    created_at: datetime
    actor_name: Optional[str] = None

    class Config:
        from_attributes = True


# ---------- Дашборд руководителя ----------

class BusinessSettingsOut(BaseModel):
    monthly_revenue_target: float

    class Config:
        from_attributes = True


class BusinessSettingsUpdate(BaseModel):
    monthly_revenue_target: float


class EmployeeRankingItem(BaseModel):
    employee_id: int
    full_name: str
    washes_count: int
    revenue: float
    payout: float


class ManagerDashboard(BaseModel):
    period_from: date
    period_to: date
    revenue_total: float
    revenue_wash: float
    revenue_dry_cleaning: float
    payouts_total: float
    profit_estimate: float          # выручка минус выплаты мастерам
    average_check: float
    loyalty_discount_cost: float    # сколько "подарили" скидками 50%/100% за период
    monthly_revenue_target: float
    monthly_progress_pct: float
    employee_ranking: List[EmployeeRankingItem] = []


# ---------- Поиск клиента (админ) ----------

class ClientSearchResult(BaseModel):
    user: UserOut
    bookings: List[BookingOut] = []
    walk_in_orders: List[WalkInOrderOut] = []
    dry_cleaning_orders: List[DryCleaningOrderOut] = []


# ---------- Назначение сотрудников на заказ (много людей на одну машину) ----------

class EmployeeAssignmentSet(BaseModel):
    employee_ids: List[int] = Field(default_factory=list)


class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    position: Optional[str] = None
    color_tag: Optional[str] = None
    is_admin_role: Optional[bool] = None
    is_active: Optional[bool] = None


# ---------- Зарплата: дневной и недельный отчёт (тестовый режим) ----------

class EmployeeDayPayout(BaseModel):
    employee_id: int
    full_name: str
    jobs_count: int
    earned_raw: float          # сколько реально насчиталось до гарантии
    guarantee_applied: bool    # сработала ли доплата-неустойка до минимума
    final_payout: float


class DailyPayrollOut(BaseModel):
    date: date
    total_revenue: float
    admin_on_duty: List[str] = Field(default_factory=list)
    employees: List[EmployeeDayPayout] = []


class WeeklyEmployeePayout(BaseModel):
    employee_id: int
    full_name: str
    days_worked: int
    jobs_count: int
    total_payout: float


class WeeklyPayrollOut(BaseModel):
    date_from: date
    date_to: date
    total_revenue: float
    employees: List[WeeklyEmployeePayout] = []
