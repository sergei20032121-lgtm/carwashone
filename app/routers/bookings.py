from datetime import date, datetime, time, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Booking, Service, User, UserRole, BookingStatus
from app.schemas import BookingCreate, BookingOut, BookingUpdate
from app.dependencies import get_current_user, require_staff
from app.loyalty import register_wash, price_with_discount

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
        scheduled_at=data.scheduled_at,
        comment=data.comment,
        price=price_with_discount(service.price_from, preview_discount),
        discount_pct=preview_discount,
        status=BookingStatus.PENDING,
    )
    db.add(booking)
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
    Упрощённая логика: рабочие часы 09:00–21:00 с шагом 30 минут,
    минус уже занятые слоты в этот день. Реальная логика (боксы,
    занятость мастеров по 'Графику') подключается на следующем шаге.
    """
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
        minutes = t.hour * 60 + t.minute + 30
        t = time(minutes // 60, minutes % 60)
    return {"date": str(day), "slots": slots}


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


@router.patch(
    "/admin/{booking_id}",
    response_model=BookingOut,
    dependencies=[Depends(require_staff)],
    summary="Изменить статус/мастера/бокс записи",
)
def update_booking(booking_id: int, data: BookingUpdate, db: Session = Depends(get_db)):
    booking = db.query(Booking).get(booking_id)
    if not booking:
        raise HTTPException(404, "Запись не найдена")

    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(booking, k, v)

    # Начисляем ананас окончательно только когда мойка реально завершена,
    # и только один раз на запись (защита от повторного PATCH со статусом done)
    if booking.status == BookingStatus.DONE and not booking.loyalty_applied:
        client = db.query(User).get(booking.client_id)
        service = db.query(Service).get(booking.service_id)
        result = register_wash(db, client, service, booking_id=booking.id)
        if result.applied:
            booking.discount_pct = result.discount_pct
            booking.price = price_with_discount(service.price_from, result.discount_pct)
        booking.loyalty_applied = True

    db.commit()
    db.refresh(booking)
    return booking
