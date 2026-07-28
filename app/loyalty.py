"""
Бонусная карта «Автомойка №1»:
- за каждую ПОЛНУЮ мойку (Service.counts_towards_loyalty=True) на карту
  ставится ананас;
- 6-й ананас — скидка 50% на эту мойку;
- 12-й ананас — эта мойка бесплатная, после чего карта обнуляется и
  начинается новый цикл.

Карта — это просто счётчик User.punch_count (0-11 в рамках текущего цикла).
User.total_full_washes — общее количество полных моек за всё время (для статистики,
не сбрасывается).
"""
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models import User, Service, PineappleStampLog


@dataclass
class StampResult:
    applied: bool
    stamp_number: int = 0        # позиция на карте (1-12), 0 если не применялось
    discount_pct: int = 0        # 0 / 50 / 100
    punch_count_after: int = 0   # что показывать на карте после этой мойки


def register_wash(
    db: Session,
    user: User,
    service: Service,
    booking_id: Optional[int] = None,
    walk_in_order_id: Optional[int] = None,
) -> StampResult:
    """Начислить ананас, если услуга считается 'полной мойкой'. Возвращает применённую скидку."""
    if not service.counts_towards_loyalty:
        return StampResult(applied=False)

    stamp_number = user.punch_count + 1  # 1..12
    discount = 0
    if stamp_number == 6:
        discount = 50
    elif stamp_number == 12:
        discount = 100

    user.total_full_washes = (user.total_full_washes or 0) + 1
    user.punch_count = 0 if stamp_number == 12 else stamp_number

    db.add(PineappleStampLog(
        user_id=user.id,
        booking_id=booking_id,
        walk_in_order_id=walk_in_order_id,
        stamp_number=stamp_number,
        discount_applied_pct=discount,
    ))

    return StampResult(applied=True, stamp_number=stamp_number, discount_pct=discount, punch_count_after=user.punch_count)


def price_with_discount(price: float, discount_pct: int) -> float:
    return round(price * (1 - discount_pct / 100), 2)


def calc_employee_payout(price: float, payout_pct: float) -> float:
    """З/П мастера — процент от итоговой цены услуги (по умолчанию 35% для мойки,
    настраивается per-service через Service.payout_pct)."""
    if not price or not payout_pct:
        return 0.0
    return round(price * (payout_pct / 100), 2)
