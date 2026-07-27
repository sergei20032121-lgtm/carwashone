from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Booking, DryCleaningOrder, WalkInOrder, BookingStatus
from app.schemas import StatsSummary
from app.dependencies import require_staff

router = APIRouter(prefix="/admin/stats", tags=["Статистика (админ)"])


@router.get("/summary", response_model=StatsSummary, dependencies=[Depends(require_staff)])
def summary(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
):
    date_to = date_to or date.today()
    date_from = date_from or (date_to - timedelta(days=30))

    wash_q = db.query(Booking).filter(
        func.date(Booking.scheduled_at) >= date_from,
        func.date(Booking.scheduled_at) <= date_to,
        Booking.status != BookingStatus.CANCELLED,
    )
    walk_in_q = db.query(WalkInOrder).filter(
        WalkInOrder.order_date >= date_from,
        WalkInOrder.order_date <= date_to,
    )
    dry_q = db.query(DryCleaningOrder).filter(
        DryCleaningOrder.order_date >= date_from,
        DryCleaningOrder.order_date <= date_to,
    )

    return StatsSummary(
        period_from=date_from,
        period_to=date_to,
        wash_bookings_count=wash_q.count() + walk_in_q.count(),
        wash_revenue=sum(b.price or 0 for b in wash_q.all()) + sum(o.amount or 0 for o in walk_in_q.all()),
        dry_cleaning_orders_count=dry_q.count(),
        dry_cleaning_revenue=sum(o.amount or 0 for o in dry_q.all()),
        dry_cleaning_payouts=sum(o.employee_payout or 0 for o in dry_q.all()),
    )
