from datetime import date, datetime, time, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Booking, Service, User, UserRole, BookingStatus, AuditLog, JobAssignment, Employee, CarProfile
from app.schemas import BookingCreate, BookingOut, BookingUpdate, RatingSubmit, EmployeeAssignmentSet
from app.dependencies import get_current_user, require_staff
from app.loyalty import register_wash, price_with_discount, calc_employee_payout
from app.payroll import get_business_settings
from app.config import settings as app_settings

router = APIRouter(prefix="/bookings", tags=["Запись на мойку"])


@router.post("", response_model=BookingOut, summary="Создать запись (клиент, после смс-подтверждения)")
def create_booking(
    data: BookingCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = db.query(Service).get(data.service_id)
    if not service or not service.is_active:
        raise HTTPException(404, "Услуга не найдена")

    scheduled_at = data.scheduled_at
    if scheduled_at.tzinfo is not None:
        scheduled_at = scheduled_at.astimezone(ZoneInfo(app_settings.business_timezone)).replace(tzinfo=None)

    business_now = datetime.now(ZoneInfo(app_settings.business_timezone)).replace(tzinfo=None)
    business_today = business_now.date()
    if scheduled_at <= business_now:
        raise HTTPException(400, "Нельзя записаться на прошедшее время")
    if scheduled_at.time() < time(9, 0) or scheduled_at.time() >= time(21, 0):
        raise HTTPException(400, "Онлайн-запись доступна с 09:00 до 21:00")

    if data.car_profile_id:
        car = (
            db.query(CarProfile)
            .filter(CarProfile.id == data.car_profile_id, CarProfile.user_id == user.id)
            .first()
        )
        if not car:
            raise HTTPException(400, "Выбранный автомобиль не найден в вашем кабинете")

    # Клиент видит и может записаться онлайн только на ближайшие N дней (по умолчанию 3) —
    # дальше по ТЗ "обговаривается по телефону". Персонал (админ/мойщик) это ограничение не касается.
    if user.role == UserRole.CLIENT:
        settings = get_business_settings(db)
        max_date = business_today + timedelta(days=settings.client_booking_window_days)
        if scheduled_at.date() > max_date:
            raise HTTPException(
                400,
                f"Онлайн запись доступна максимум на {settings.client_booking_window_days} дн. вперёд — "
                f"на более поздние даты, пожалуйста, звоните нам по телефону.",
            )

    slot_is_taken = (
        db.query(Booking)
        .filter(
            Booking.scheduled_at == scheduled_at,
            Booking.status != BookingStatus.CANCELLED,
        )
        .first()
    )
    if slot_is_taken:
        raise HTTPException(409, "Это время уже занято. Выберите другой свободный слот.")

    # Превью скидки по карте — покажем клиенту сразу, чек начислится по факту при завершении мойки
    preview_discount = 0
    if service.counts_towards_loyalty:
        next_stamp = user.punch_count + 1
        if next_stamp == 6:
            preview_discount = 50
        elif next_stamp == 12:
            preview_discount = 100

    booking = Booking(
        client_id=user.id,
        service_id=service.id,
        car_profile_id=data.car_profile_id,
        scheduled_at=scheduled_at,
        comment=data.comment,
        price=price_with_discount(service.price_from, preview_discount),
        discount_pct=preview_discount,
        status=BookingStatus.PENDING,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


@router.get("/last", response_model=Optional[BookingOut], summary="Последняя запись клиента (для 'повторить мойку')")
def last_booking(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(Booking)
        .filter(Booking.client_id == user.id)
        .order_by(Booking.scheduled_at.desc())
        .first()
    )


@router.post("/{booking_id}/rate", response_model=BookingOut, summary="Оценить мастера после мойки (1-5)")
def rate_booking(booking_id: int, data: RatingSubmit, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    booking = db.query(Booking).filter(Booking.id == booking_id, Booking.client_id == user.id).first()
    if not booking:
        raise HTTPException(404, "Запись не найдена")
    if booking.status != BookingStatus.DONE:
        raise HTTPException(400, "Оценить можно только выполненную запись")
    booking.rating = data.rating
    booking.rating_comment = data.comment
    db.commit()
    db.refresh(booking)
    return booking


@router.get("/me", response_model=List[BookingOut], summary="Мои записи")
def my_bookings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(Booking)
        .filter(Booking.client_id == user.id)
        .order_by(Booking.scheduled_at.desc())
        .all()
    )


@router.get("/slots", summary="Свободные слоты на день (публично, для формы записи)")
def free_slots(day: date, db: Session = Depends(get_db)):
    """
    Рабочие часы 09:00–21:00, шаг — из настроек бизнеса (60/30/15/10 минут).
    Реальная занятость по боксам/мастерам подключается отдельно от графика смен.
    """
    settings = get_business_settings(db)
    step = settings.slot_granularity_minutes or 30

    taken = {
        b.scheduled_at.time()
        for b in db.query(Booking)
        .filter(
            Booking.scheduled_at >= datetime.combine(day, time.min),
            Booking.scheduled_at <= datetime.combine(day, time.max),
            Booking.status != BookingStatus.CANCELLED,
        )
        .all()
    }
    slots = []
    t = time(9, 0)
    end = time(21, 0)
    while t < end:
        slots.append({"time": t.strftime("%H:%M"), "available": t not in taken})
        minutes = t.hour * 60 + t.minute + step
        t = time(minutes // 60, minutes % 60)

    business_today = datetime.now(ZoneInfo(app_settings.business_timezone)).date()
    max_online_date = business_today + timedelta(days=settings.client_booking_window_days)
    return {
        "date": str(day),
        "slots": slots,
        "within_online_window": day <= max_online_date,
        "max_online_date": str(max_online_date),
    }


# ---------------------- Админ / сотрудники ----------------------

@router.get(
    "/admin/all",
    response_model=List[BookingOut],
    dependencies=[Depends(require_staff)],
    summary="Все записи (админ/сотрудник)",
)
def all_bookings(
    status_filter: Optional[BookingStatus] = None,
    day: Optional[date] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Booking)
    if status_filter:
        q = q.filter(Booking.status == status_filter)
    if day:
        q = q.filter(
            Booking.scheduled_at >= datetime.combine(day, time.min),
            Booking.scheduled_at <= datetime.combine(day, time.max),
        )
    return q.order_by(Booking.scheduled_at).all()


@router.put(
    "/admin/{booking_id}/employees", response_model=BookingOut,
    dependencies=[Depends(require_staff)],
    summary="Назначить сотрудников на запись (кто мыл машину)",
)
def assign_booking_employees(booking_id: int, data: EmployeeAssignmentSet, db: Session = Depends(get_db)):
    booking = db.query(Booking).get(booking_id)
    if not booking:
        raise HTTPException(404, "Запись не найдена")
    db.query(JobAssignment).filter(JobAssignment.order_type == "booking", JobAssignment.order_id == booking_id).delete()
    for emp_id in data.employee_ids:
        if not db.query(Employee).get(emp_id):
            raise HTTPException(400, f"Сотрудник id={emp_id} не найден")
        db.add(JobAssignment(order_type="booking", order_id=booking_id, employee_id=emp_id))
    booking.employee_id = data.employee_ids[0] if data.employee_ids else None
    db.commit()
    db.refresh(booking)
    return booking


@router.patch(
    "/admin/{booking_id}",
    response_model=BookingOut,
    summary="Изменить статус/мастера/бокс записи",
)
def update_booking(booking_id: int, data: BookingUpdate, actor: User = Depends(require_staff), db: Session = Depends(get_db)):
    booking = db.query(Booking).get(booking_id)
    if not booking:
        raise HTTPException(404, "Запись не найдена")

    changes = data.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(booking, k, v)

    # Начисляем ананас и з/п мастера окончательно только когда мойка реально
    # завершена, и только один раз на запись (защита от повторного PATCH со статусом done)
    if booking.status == BookingStatus.DONE and not booking.loyalty_applied:
        client = db.query(User).get(booking.client_id)
        service = db.query(Service).get(booking.service_id)
        result = register_wash(db, client, service, booking_id=booking.id)
        if result.applied:
            booking.discount_pct = result.discount_pct
            booking.price = price_with_discount(service.price_from, result.discount_pct)
        booking.employee_payout = calc_employee_payout(booking.price, service.payout_pct)
        booking.loyalty_applied = True

    db.add(AuditLog(
        actor_user_id=actor.id, action="update", entity="booking", entity_id=booking.id,
        note=f"Изменено: {', '.join(changes.keys())}",
    ))
    db.commit()
    db.refresh(booking)
    return booking
