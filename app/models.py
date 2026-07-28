import enum
from datetime import datetime, date

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date, ForeignKey,
    Enum as SAEnum, Text, JSON
)
from sqlalchemy.orm import relationship

from app.database import Base


# ---------------------------------------------------------------------------
# Справочники / роли
# ---------------------------------------------------------------------------

class UserRole(str, enum.Enum):
    CLIENT = "client"       # обычный клиент, вход только по телефону + смс-код
    MASTER = "master"       # сотрудник (мойщик / химчист)
    ADMIN = "admin"         # администратор — полный доступ
    MANAGER = "manager"     # руководитель — доступ только на чтение, KPI/аналитика


class ServiceCategory(str, enum.Enum):
    WASH = "wash"                   # обычная мойка (экспресс/комплекс/детейлинг/защита)
    DRY_CLEANING = "dry_cleaning"   # химчистка — отдельный раздел по ТЗ


class BookingStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class ShiftType(str, enum.Enum):
    FULL_DAY = "full_day"        # Полный день
    DAY_9_18 = "day_9_18"        # 09:00-18:00
    EVENING_17_22 = "evening_17_22"  # 17:00-22:00
    DAY_OFF = "day_off"          # выходной
    NO_SHOW = "no_show"          # невыход


# ---------------------------------------------------------------------------
# Пользователи и сотрудники
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    phone = Column(String(20), unique=True, index=True, nullable=True)
    username = Column(String(60), unique=True, index=True, nullable=True)  # для входа персонала/админа
    full_name = Column(String(120), nullable=True)
    role = Column(SAEnum(UserRole), default=UserRole.CLIENT, nullable=False)

    # пароль нужен только сотрудникам/админам (у клиентов вход по смс-коду, без пароля)
    password_hash = Column(String(255), nullable=True)

    # --- бонусная карта: печать за каждую ПОЛНУЮ мойку (комплекс и выше) ---
    # punch_count — сколько ананасов уже на текущей карте (0-11, после 12-й сбрасывается)
    # total_full_washes — сколько всего полных моек за всё время (для статистики)
    punch_count = Column(Integer, default=0)
    total_full_washes = Column(Integer, default=0)

    car_plate = Column(String(20), nullable=True)
    birthday = Column(Date, nullable=True)  # для поздравления/бонуса в день рождения

    # --- реферальная программа ---
    referral_code = Column(String(12), unique=True, index=True, nullable=True)
    referred_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    bookings = relationship("Booking", back_populates="client")
    employee_profile = relationship("Employee", back_populates="user", uselist=False)
    cars = relationship("CarProfile", back_populates="owner")

    @property
    def tenure_label(self) -> str:
        """Бейдж 'с нами N месяцев/лет' по дате регистрации."""
        days = (datetime.utcnow() - self.created_at).days if self.created_at else 0
        if days < 30:
            return "Новый клиент"
        months = days // 30
        if months < 12:
            return f"С нами {months} мес."
        years = months // 12
        return f"С нами {years} г."


class CarProfile(Base):
    """Сохранённые машины клиента — чтобы при записи не вбивать заново."""
    __tablename__ = "car_profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    brand = Column(String(80), nullable=False)   # "Toyota Mark II"
    plate = Column(String(20), nullable=True)
    nickname = Column(String(60), nullable=True)  # "моя основная", "жены" и т.п.
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="cars")


class OTPCode(Base):
    """Одноразовый код для входа/записи по номеру телефона."""
    __tablename__ = "otp_codes"

    id = Column(Integer, primary_key=True)
    phone = Column(String(20), index=True, nullable=False)
    code = Column(String(6), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Employee(Base):
    """Сотрудник мойки/химчистки — для графика и распределения записей."""
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    full_name = Column(String(120), nullable=False)
    position = Column(String(60), default="Мойщик")  # Мойщик / Химчист / Администратор
    color_tag = Column(String(20), default="#00C2CB")  # для отображения в графике
    is_active = Column(Boolean, default=True)

    user = relationship("User", back_populates="employee_profile")
    shifts = relationship("ShiftSchedule", back_populates="employee")


class ShiftSchedule(Base):
    """Аналог листа 'График.xlsx' — по дню и сотруднику один тип смены."""
    __tablename__ = "shift_schedule"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    work_date = Column(Date, nullable=False)
    shift_type = Column(SAEnum(ShiftType), default=ShiftType.DAY_OFF)
    note = Column(String(255), nullable=True)

    employee = relationship("Employee", back_populates="shifts")


# ---------------------------------------------------------------------------
# Услуги
# ---------------------------------------------------------------------------

class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True)
    category = Column(SAEnum(ServiceCategory), nullable=False)
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    price_from = Column(Float, nullable=False)
    price_to = Column(Float, nullable=True)   # если есть вилка цены (напр. 1300–2100 ₽); иначе просто "от"
    duration_min = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)

    # % от суммы услуги, который уходит мастеру как з/п (напр. 35 для обычной мойки)
    payout_pct = Column(Float, default=0)

    # считается ли эта услуга "полной мойкой" для бонусной карты (ставим ананас)
    # Экспресс/облив — не считаются, Комплекс и всё дороже — считаются
    counts_towards_loyalty = Column(Boolean, default=False)

    bookings = relationship("Booking", back_populates="service")


# ---------------------------------------------------------------------------
# Запись (мойка)
# ---------------------------------------------------------------------------

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    car_profile_id = Column(Integer, ForeignKey("car_profiles.id"), nullable=True)

    scheduled_at = Column(DateTime, nullable=False)
    box_number = Column(Integer, nullable=True)
    status = Column(SAEnum(BookingStatus), default=BookingStatus.PENDING)
    price = Column(Float, nullable=True)
    discount_pct = Column(Integer, default=0)  # применённая скидка по карте (0/50/100)
    employee_payout = Column(Float, nullable=True)  # з/п мастера (% от цены услуги, считается автоматически)
    comment = Column(String(255), nullable=True)
    loyalty_applied = Column(Boolean, default=False)  # чтобы не насчитать ананас дважды

    rating = Column(Integer, nullable=True)          # оценка мастера клиентом, 1-5
    rating_comment = Column(String(255), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("User", back_populates="bookings")
    service = relationship("Service", back_populates="bookings")
    employee = relationship("Employee")


# ---------------------------------------------------------------------------
# Химчистка — отдельный журнал заказов (как в Химчистка.xlsx)
# ---------------------------------------------------------------------------

class DryCleaningOrder(Base):
    __tablename__ = "dry_cleaning_orders"

    id = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)

    order_date = Column(Date, nullable=False)
    car_model = Column(String(80), nullable=False)
    works_description = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=True)

    amount = Column(Float, nullable=False)          # сумма заказа
    employee_payout = Column(Float, nullable=True)   # з/п мастера с заказа

    # фото "до/после" — пришлёшь позже, пока просто список URL в JSON
    photos_before = Column(JSON, default=list)
    photos_after = Column(JSON, default=list)

    status = Column(SAEnum(BookingStatus), default=BookingStatus.DONE)
    created_at = Column(DateTime, default=datetime.utcnow)

    employee = relationship("Employee")


# ---------------------------------------------------------------------------
# Разовые заказы без предварительной записи — журнал по образцу "Учёт.xlsx"
# (клиент просто приехал, сотрудник заносит заказ вручную; так фиксировалось
#  ~5500 заказов за последние 30 месяцев в твоём файле)
# ---------------------------------------------------------------------------

class WalkInOrder(Base):
    __tablename__ = "walk_in_orders"

    id = Column(Integer, primary_key=True)
    order_date = Column(Date, nullable=False)
    time_note = Column(String(20), nullable=True)  # как в экселе — иногда просто время текстом

    service_id = Column(Integer, ForeignKey("services.id"), nullable=True)
    service_name_raw = Column(String(120), nullable=False)  # "Комплексная", "Экспресс" и т.п.
    extra_service = Column(String(120), nullable=True)      # "Доп. услуга" — коврики, полироль и т.д.
    car_model = Column(String(120), nullable=True)

    amount = Column(Float, nullable=False)
    employee_payout = Column(Float, nullable=True)  # з/п мастера (% от суммы, считается автоматически)
    contact_name = Column(String(120), nullable=True)  # "Контакт" из журнала — имя/номер клиента
    client_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # если удалось привязать к клиенту

    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    service = relationship("Service")
    employee = relationship("Employee")


# ---------------------------------------------------------------------------
# Лояльность — журнал начислений ананасов на карту
# ---------------------------------------------------------------------------

class PineappleStampLog(Base):
    __tablename__ = "pineapple_stamp_log"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True)
    walk_in_order_id = Column(Integer, ForeignKey("walk_in_orders.id"), nullable=True)

    stamp_number = Column(Integer, nullable=False)   # позиция на карте на момент начисления (1-12)
    discount_applied_pct = Column(Integer, default=0)  # 0 / 50 / 100
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# 2ГИС — настройки заведения + кэш отзывов
# ---------------------------------------------------------------------------

class GisSettings(Base):
    """Единственная запись-настройка: ссылка на филиал, org_id, api key."""
    __tablename__ = "gis_settings"

    id = Column(Integer, primary_key=True)
    org_id = Column(String(60), nullable=True)
    org_url = Column(String(255), nullable=True)
    api_key = Column(String(120), nullable=True)
    rating = Column(Float, nullable=True)
    reviews_count = Column(Integer, nullable=True)
    last_synced_at = Column(DateTime, nullable=True)


class GisReview(Base):
    """Кэш отзывов, подтянутых с 2ГИС (заполняется синком, когда дадите API/ссылку)."""
    __tablename__ = "gis_reviews"

    id = Column(Integer, primary_key=True)
    external_id = Column(String(80), unique=True, nullable=False)
    author_name = Column(String(120), nullable=True)
    rating = Column(Integer, nullable=True)
    text = Column(Text, nullable=True)
    published_at = Column(DateTime, nullable=True)
    fetched_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# ВКонтакте — настройки группы + кэш постов (новости на сайт)
# ---------------------------------------------------------------------------

class VkSettings(Base):
    """Единственная запись-настройка: домен группы и токен доступа VK API."""
    __tablename__ = "vk_settings"

    id = Column(Integer, primary_key=True)
    group_domain = Column(String(120), nullable=True)   # например 'carwash_one_zkm'
    access_token = Column(String(255), nullable=True)    # НЕ храним в git, только в БД/переменных окружения
    last_synced_at = Column(DateTime, nullable=True)


class VkPost(Base):
    """Кэш постов со стены группы — рендерится как сетка новостей на сайте."""
    __tablename__ = "vk_posts"

    id = Column(Integer, primary_key=True)
    vk_post_id = Column(Integer, unique=True, nullable=False)
    text = Column(Text, nullable=True)
    photo_urls = Column(JSON, default=list)   # ссылки на прикреплённые фото поста
    likes = Column(Integer, default=0)
    published_at = Column(DateTime, nullable=True)
    is_pinned = Column(Boolean, default=False)
    fetched_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Аудит — кто и что поменял в админке (важно, когда работает несколько человек)
# ---------------------------------------------------------------------------

class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(30), nullable=False)     # create / update / delete
    entity = Column(String(60), nullable=False)      # "booking", "walk_in_order", "service" и т.п.
    entity_id = Column(Integer, nullable=True)
    note = Column(Text, nullable=True)               # краткое описание изменения
    created_at = Column(DateTime, default=datetime.utcnow)

    actor = relationship("User")


# ---------------------------------------------------------------------------
# Подарочные сертификаты
# ---------------------------------------------------------------------------

class GiftCertificate(Base):
    __tablename__ = "gift_certificates"

    id = Column(Integer, primary_key=True)
    code = Column(String(20), unique=True, nullable=False)
    amount = Column(Float, nullable=False)
    issued_to_phone = Column(String(20), nullable=True)
    is_used = Column(Boolean, default=False)
    used_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------------------
# Настройки бизнеса — цель по выручке для дашборда руководителя
# ---------------------------------------------------------------------------

class BusinessSettings(Base):
    __tablename__ = "business_settings"

    id = Column(Integer, primary_key=True)
    monthly_revenue_target = Column(Float, default=0)
