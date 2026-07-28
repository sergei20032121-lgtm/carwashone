"""
Публичные "живые" данные для витрины сайта — специально НЕ выдуманные,
только реальная активность из базы (анонимизированная). Никакой имитации
фейковой социальной активности — это было бы обманом.
"""
from collections import defaultdict
from datetime import datetime, timedelta, date, time as dtime
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import WalkInOrder, Booking, BookingStatus
from app.schemas import RecentActivityItem, BusyHoursOut, CurrentLoadOut

router = APIRouter(prefix="/public", tags=["Публичная витрина"])


def _anonymize(name: str) -> str:
    """'Иван Петров' -> 'Иван П.'; одно слово -> как есть; пусто -> 'Клиент'."""
    if not name:
        return "Клиент"
    parts = name.strip().split()
    if len(parts) >= 2:
        return f"{parts[0]} {parts[1][0]}."
    return parts[0]


@router.get("/recent-activity", response_model=List[RecentActivityItem], summary="Реальная недавняя активность (анонимно)")
def recent_activity(db: Session = Depends(get_db)):
    since = datetime.utcnow() - timedelta(hours=6)
    items = []

    walk_ins = (
        db.query(WalkInOrder)
        .filter(WalkInOrder.created_at >= since)
        .order_by(WalkInOrder.created_at.desc())
        .limit(5)
        .all()
    )
    for o in walk_ins:
        items.append({
            "name": _anonymize(o.contact_name),
            "service_label": o.service_name_raw,
            "when": o.created_at,
        })

    bookings = (
        db.query(Booking)
        .filter(Booking.created_at >= since, Booking.status != BookingStatus.CANCELLED)
        .order_by(Booking.created_at.desc())
        .limit(5)
        .all()
    )
    for b in bookings:
        client_name = b.client.full_name if b.client else None
        items.append({
            "name": _anonymize(client_name),
            "service_label": b.service.name if b.service else "Мойка",
            "when": b.created_at,
        })

    items.sort(key=lambda i: i["when"], reverse=True)
    return items[:6]


@router.get("/busy-hours", response_model=BusyHoursOut, summary="Загруженность по часам за последние 30 дней (реальная статистика)")
def busy_hours(db: Session = Depends(get_db)):
    since = date.today() - timedelta(days=30)
    counts = defaultdict(int)

    for o in db.query(WalkInOrder).filter(WalkInOrder.order_date >= since).all():
        if o.time_note and ":" in o.time_note:
            try:
                hour = int(o.time_note.split(":")[0])
                counts[hour] += 1
            except ValueError:
                continue

    for b in db.query(Booking).filter(
        func.date(Booking.scheduled_at) >= since, Booking.status != BookingStatus.CANCELLED
    ).all():
        counts[b.scheduled_at.hour] += 1

    max_count = max(counts.values()) if counts else 1
    hours = list(range(9, 21))
    load = [
        {"hour": h, "load_pct": round((counts.get(h, 0) / max_count) * 100) if max_count else 0}
        for h in hours
    ]
    has_data = bool(counts)
    return {"hours": load, "has_data": has_data}


@router.get("/current-load", response_model=CurrentLoadOut, summary="Насколько загружено прямо сейчас (по количеству броней рядом с текущим временем)")
def current_load(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    window_start = now - timedelta(minutes=45)
    window_end = now + timedelta(minutes=45)

    active = (
        db.query(Booking)
        .filter(
            Booking.scheduled_at >= window_start,
            Booking.scheduled_at <= window_end,
            Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED, BookingStatus.IN_PROGRESS]),
        )
        .count()
    )

    # предполагаем условно 3 одновременных бокса — просто ориентир для цвета индикатора
    capacity = 3
    if active == 0:
        level = "low"
    elif active < capacity:
        level = "medium"
    else:
        level = "high"

    return {"active_count": active, "capacity": capacity, "level": level}
