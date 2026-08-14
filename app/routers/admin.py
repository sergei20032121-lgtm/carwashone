from datetime import date, datetime, time, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Booking, DryCleaningOrder, WalkInOrder, BookingStatus,
    Employee, PineappleStampLog, Service, AuditLog, User, BusinessSettings, CommunicationLog,
)
from app.schemas import (
    StatsSummary, ManagerDashboard, EmployeeRankingItem,
    ClientSearchResult, TimelineEvent, AuditLogOut, BusinessSettingsOut, BusinessSettingsUpdate,
)
from app.dependencies import require_staff, require_admin, require_manager_or_admin
from app import payroll
from app.schemas import DailyPayrollOut, WeeklyPayrollOut

router = APIRouter(prefix="/admin", tags=["Статистика (админ)"])


@router.get("/stats/summary", response_model=StatsSummary, dependencies=[Depends(require_staff)])
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


# ---------------------------------------------------------------------------
# Дашборд руководителя — только чтение (роль manager или admin)
# ---------------------------------------------------------------------------

def _period_totals(db: Session, date_from: date, date_to: date):
    walk_in_q = db.query(WalkInOrder).filter(
        WalkInOrder.order_date >= date_from, WalkInOrder.order_date <= date_to,
    )
    dry_q = db.query(DryCleaningOrder).filter(
        DryCleaningOrder.order_date >= date_from, DryCleaningOrder.order_date <= date_to,
    )
    booking_q = db.query(Booking).filter(
        func.date(Booking.scheduled_at) >= date_from,
        func.date(Booking.scheduled_at) <= date_to,
        Booking.status == BookingStatus.DONE,
    )

    walk_in_orders = walk_in_q.all()
    dry_orders = dry_q.all()
    bookings = booking_q.all()

    revenue_wash = sum(o.amount or 0 for o in walk_in_orders) + sum(b.price or 0 for b in bookings)
    revenue_dry = sum(o.amount or 0 for o in dry_orders)
    payouts = (
        sum(o.employee_payout or 0 for o in walk_in_orders)
        + sum(o.employee_payout or 0 for o in dry_orders)
    )
    orders_count = len(walk_in_orders) + len(dry_orders) + len(bookings)

    return {
        "revenue_wash": revenue_wash,
        "revenue_dry": revenue_dry,
        "revenue_total": revenue_wash + revenue_dry,
        "payouts": payouts,
        "orders_count": orders_count,
    }


@router.get(
    "/manager/dashboard", response_model=ManagerDashboard,
    dependencies=[Depends(require_manager_or_admin)],
    summary="Дашборд руководителя: выручка, прибыль, рейтинг сотрудников, цена лояльности",
)
def manager_dashboard(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
):
    date_to = date_to or date.today()
    date_from = date_from or (date_to - timedelta(days=30))

    totals = _period_totals(db, date_from, date_to)
    avg_check = totals["revenue_total"] / totals["orders_count"] if totals["orders_count"] else 0

    # цена программы лояльности — оценка: сколько "подарили" скидками 50%/100% за период.
    # Считаем от текущей цены услуги (историю цены на момент скидки не храним, это оценка).
    stamps = (
        db.query(PineappleStampLog)
        .filter(
            PineappleStampLog.discount_applied_pct > 0,
            PineappleStampLog.created_at >= date_from,
            PineappleStampLog.created_at <= date_to + timedelta(days=1),
        )
        .all()
    )
    loyalty_cost = 0.0
    for s in stamps:
        booking = db.query(Booking).get(s.booking_id) if s.booking_id else None
        service = db.query(Service).get(booking.service_id) if booking else None
        base_price = service.price_from if service else 0
        loyalty_cost += base_price * (s.discount_applied_pct / 100)

    # рейтинг сотрудников по walk-in + химчистке (где employee_id проставлен)
    employees = db.query(Employee).filter(Employee.is_active == True).all()  # noqa: E712
    ranking = []
    for emp in employees:
        w_orders = db.query(WalkInOrder).filter(
            WalkInOrder.employee_id == emp.id,
            WalkInOrder.order_date >= date_from, WalkInOrder.order_date <= date_to,
        ).all()
        d_orders = db.query(DryCleaningOrder).filter(
            DryCleaningOrder.employee_id == emp.id,
            DryCleaningOrder.order_date >= date_from, DryCleaningOrder.order_date <= date_to,
        ).all()
        count = len(w_orders) + len(d_orders)
        if count == 0:
            continue
        revenue = sum(o.amount or 0 for o in w_orders) + sum(o.amount or 0 for o in d_orders)
        payout = sum(o.employee_payout or 0 for o in w_orders) + sum(o.employee_payout or 0 for o in d_orders)
        ranking.append(EmployeeRankingItem(
            employee_id=emp.id, full_name=emp.full_name,
            washes_count=count, revenue=revenue, payout=payout,
        ))
    ranking.sort(key=lambda r: r.revenue, reverse=True)

    business = db.query(BusinessSettings).first()
    target = business.monthly_revenue_target if business else 0
    # прогресс считаем от выручки текущего календарного месяца, а не произвольного периода
    month_start = date.today().replace(day=1)
    month_totals = _period_totals(db, month_start, date.today())
    progress_pct = (month_totals["revenue_total"] / target * 100) if target else 0

    return ManagerDashboard(
        period_from=date_from,
        period_to=date_to,
        revenue_total=totals["revenue_total"],
        revenue_wash=totals["revenue_wash"],
        revenue_dry_cleaning=totals["revenue_dry"],
        payouts_total=totals["payouts"],
        profit_estimate=totals["revenue_total"] - totals["payouts"],
        average_check=round(avg_check, 2),
        loyalty_discount_cost=round(loyalty_cost, 2),
        monthly_revenue_target=target,
        monthly_progress_pct=round(progress_pct, 1),
        employee_ranking=ranking,
    )


@router.get("/business-settings", response_model=BusinessSettingsOut, dependencies=[Depends(require_admin)])
def get_business_settings(db: Session = Depends(get_db)):
    row = db.query(BusinessSettings).first()
    if not row:
        row = BusinessSettings(monthly_revenue_target=0)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.put("/business-settings", response_model=BusinessSettingsOut, dependencies=[Depends(require_admin)])
def update_business_settings(data: BusinessSettingsUpdate, db: Session = Depends(get_db)):
    row = db.query(BusinessSettings).first()
    if not row:
        row = BusinessSettings()
        db.add(row)
    row.monthly_revenue_target = data.monthly_revenue_target
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Поиск клиента по телефону — вся история в одном месте
# ---------------------------------------------------------------------------

@router.get(
    "/payroll/daily", response_model=DailyPayrollOut,
    dependencies=[Depends(require_manager_or_admin)],
    summary="Зарплата за день (тестовый режим) — по всем сотрудникам",
)
def payroll_daily(day: date, db: Session = Depends(get_db)):
    return payroll.compute_daily_payroll(db, day)


@router.get(
    "/payroll/weekly", response_model=WeeklyPayrollOut,
    dependencies=[Depends(require_manager_or_admin)],
    summary="Зарплата за период (тестовый режим) — итоги по неделе/периоду",
)
def payroll_weekly(date_from: date, date_to: date, db: Session = Depends(get_db)):
    if (date_to - date_from).days > 62:
        raise HTTPException(400, "Слишком большой период — максимум ~2 месяца за раз")
    return payroll.compute_weekly_payroll(db, date_from, date_to)


@router.get(
    "/search", response_model=ClientSearchResult,
    dependencies=[Depends(require_staff)],
    summary="Найти клиента по телефону — записи, разовые заказы и химчистка одним списком",
)
def search_client(phone: str, db: Session = Depends(get_db)):
    digits = "".join(ch for ch in phone if ch.isdigit() or ch == "+")
    user = db.query(User).filter(User.phone.contains(digits[-10:] if len(digits) >= 10 else digits)).first()
    if not user:
        raise HTTPException(404, "Клиент с таким телефоном не найден")

    bookings = db.query(Booking).filter(Booking.client_id == user.id).order_by(Booking.scheduled_at.desc()).all()
    walk_ins = db.query(WalkInOrder).filter(WalkInOrder.client_id == user.id).order_by(WalkInOrder.order_date.desc()).all()
    # химчистка не всегда привязана к client_id напрямую — ищем по совпадению телефона
    dry_orders = db.query(DryCleaningOrder).filter(DryCleaningOrder.phone == user.phone).order_by(DryCleaningOrder.order_date.desc()).all()
    stamps = db.query(PineappleStampLog).filter(PineappleStampLog.user_id == user.id).order_by(PineappleStampLog.created_at.desc()).all()

    user_phone_tail = "".join(ch for ch in (user.phone or "") if ch.isdigit())[-10:]
    comm_logs = []
    if len(user_phone_tail) == 10:
        for row in db.query(CommunicationLog).order_by(CommunicationLog.occurred_at.desc()).limit(2000).all():
            row_tail = "".join(ch for ch in (row.phone or "") if ch.isdigit())[-10:]
            if row_tail == user_phone_tail:
                comm_logs.append(row)

    call_labels = {"answered": "Звонок принят", "missed": "Пропущенный звонок", "rejected": "Звонок отклонён", "blocked": "Звонок заблокирован", "outgoing": "Исходящий звонок"}
    booking_status_labels = {"pending": "ожидает", "confirmed": "подтверждена", "in_progress": "в работе", "done": "выполнена", "cancelled": "отменена"}
    sms_labels = {"sent": "SMS отправлено", "delivered": "SMS доставлено", "failed": "Ошибка отправки SMS"}

    timeline: List[TimelineEvent] = []
    for b in bookings:
        timeline.append(TimelineEvent(
            type="booking", occurred_at=b.scheduled_at,
            title=b.service.name if b.service else f"Услуга #{b.service_id}",
            subtitle=f"Запись · {booking_status_labels.get(b.status.value if hasattr(b.status, 'value') else b.status, b.status)}",
            amount=b.price,
        ))
    for o in walk_ins:
        timeline.append(TimelineEvent(
            type="walk_in", occurred_at=datetime.combine(o.order_date, time(12, 0)),
            title=o.service_name_raw, subtitle=f"Мойка без записи · {o.car_model or ''}".strip(" ·"),
            amount=o.amount,
        ))
    for o in dry_orders:
        timeline.append(TimelineEvent(
            type="dry_cleaning", occurred_at=datetime.combine(o.order_date, time(12, 0)),
            title="Химчистка", subtitle=f"{o.car_model} · {o.works_description}",
            amount=o.amount,
        ))
    for s in stamps:
        subtitle = "Скидка 50% на мойку" if s.discount_applied_pct == 50 else ("Мойка бесплатно" if s.discount_applied_pct == 100 else "Ананас на карту")
        timeline.append(TimelineEvent(
            type="stamp", occurred_at=s.created_at,
            title=f"Ананас №{s.stamp_number}", subtitle=subtitle,
        ))
    for row in comm_logs:
        if row.channel == "call":
            title = call_labels.get(row.status, row.status)
            subtitle = f"{'Входящий' if row.direction == 'incoming' else 'Исходящий'}"
            if row.duration_seconds:
                subtitle += f" · {row.duration_seconds // 60} мин {row.duration_seconds % 60} сек"
        else:
            title = sms_labels.get(row.status, row.status)
            subtitle = "SMS"
        timeline.append(TimelineEvent(type=row.channel, occurred_at=row.occurred_at, title=title, subtitle=subtitle))

    timeline.sort(key=lambda item: item.occurred_at, reverse=True)

    return ClientSearchResult(
        user=user, bookings=bookings, walk_in_orders=walk_ins, dry_cleaning_orders=dry_orders,
        timeline=timeline[:200],
    )


# ---------------------------------------------------------------------------
# Журнал изменений (аудит)
# ---------------------------------------------------------------------------

@router.get(
    "/audit-log", response_model=List[AuditLogOut],
    dependencies=[Depends(require_admin)],
    summary="Последние действия в админке — кто и что менял",
)
def audit_log(limit: int = 100, db: Session = Depends(get_db)):
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()
    result = []
    for r in rows:
        actor = db.query(User).get(r.actor_user_id) if r.actor_user_id else None
        result.append(AuditLogOut(
            id=r.id, action=r.action, entity=r.entity, entity_id=r.entity_id,
            note=r.note, created_at=r.created_at,
            actor_name=(actor.full_name or actor.username or actor.phone) if actor else None,
        ))
    return result
