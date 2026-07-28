"""
Расчёт зарплаты сотрудников — "тестовый режим" (оценочный, не бухгалтерский).

Правила (как согласовано):
- С каждой машины 35% (или свой payout_pct у услуги) делится ПОРОВНУ между
  всеми сотрудниками, назначенными на этот заказ (JobAssignment). Если на
  заказе три мойщика — каждому по 1/3 от этих 35%.
- Сотрудник с флагом is_admin_role, у которого в этот день есть смена
  (не "выходной"/"невыход"), получает admin_shift_pct% от суммы КАЖДОЙ
  машины за день (вся выручка дня, не только те заказы, где он значится
  мойщиком) + admin_shift_fixed рублей фиксированно за смену.
  Если админ в этот день ЕЩЁ И сам мыл конкретную машину (назначен как
  исполнитель) — за неё он получает и свою обычную долю от 35% тоже,
  в дополнение к админской надбавке.
- Гарантия дня: если итоговая сумма сотрудника за день меньше
  daily_guarantee_amount (по умолчанию 1000₽) — ему доплачивается ровно
  daily_guarantee_amount вместо фактически заработанного (не "плюс", а "до").
"""
from collections import defaultdict
from datetime import date, timedelta
from typing import List

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    WalkInOrder, DryCleaningOrder, Booking, JobAssignment,
    Employee, ShiftSchedule, ShiftType, BusinessSettings, BookingStatus,
)


def get_business_settings(db: Session) -> BusinessSettings:
    s = db.query(BusinessSettings).first()
    if not s:
        s = BusinessSettings()
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def _jobs_for_day(db: Session, day: date):
    """(order_type, order_id, amount, payout_pct) по всем заказам за день."""
    jobs = []

    for o in db.query(WalkInOrder).filter(WalkInOrder.order_date == day).all():
        pct = o.service.payout_pct if o.service else 35
        jobs.append(("walk_in", o.id, o.amount or 0, pct or 35))

    for o in db.query(DryCleaningOrder).filter(
        DryCleaningOrder.order_date == day, DryCleaningOrder.status == BookingStatus.DONE
    ).all():
        jobs.append(("dry_cleaning", o.id, o.amount or 0, 35))

    for b in db.query(Booking).filter(
        func.date(Booking.scheduled_at) == day, Booking.status == BookingStatus.DONE
    ).all():
        pct = b.service.payout_pct if b.service else 35
        jobs.append(("booking", b.id, b.price or 0, pct or 35))

    return jobs


def compute_daily_payroll(db: Session, day: date) -> dict:
    settings = get_business_settings(db)
    jobs = _jobs_for_day(db, day)

    employee_totals: dict = defaultdict(float)
    employee_jobs_count: dict = defaultdict(int)
    total_revenue_day = sum(j[2] for j in jobs)

    for order_type, order_id, amount, payout_pct in jobs:
        base_payout = amount * (payout_pct / 100)
        assignments: List[JobAssignment] = (
            db.query(JobAssignment)
            .filter(JobAssignment.order_type == order_type, JobAssignment.order_id == order_id)
            .all()
        )
        if not assignments:
            continue  # заказ без назначенных сотрудников — не на кого делить
        share = round(base_payout / len(assignments), 2)
        for a in assignments:
            a.share_amount = share
            employee_totals[a.employee_id] += share
            employee_jobs_count[a.employee_id] += 1

    # админ(ы) на смене в этот день — надбавка 5% от всей выручки дня + фикс
    admin_on_duty = (
        db.query(Employee)
        .join(ShiftSchedule, ShiftSchedule.employee_id == Employee.id)
        .filter(
            Employee.is_admin_role == True,  # noqa: E712
            ShiftSchedule.work_date == day,
            ShiftSchedule.shift_type.notin_([ShiftType.DAY_OFF, ShiftType.NO_SHOW]),
        )
        .all()
    )
    for emp in admin_on_duty:
        bonus = total_revenue_day * (settings.admin_shift_pct / 100) + settings.admin_shift_fixed
        employee_totals[emp.id] += bonus

    # сотрудники, у которых просто была смена в этот день (даже если не заработали ничего) —
    # тоже должны попасть в отчёт, чтобы гарантия сработала и по ним
    shift_today = (
        db.query(Employee)
        .join(ShiftSchedule, ShiftSchedule.employee_id == Employee.id)
        .filter(
            ShiftSchedule.work_date == day,
            ShiftSchedule.shift_type.notin_([ShiftType.DAY_OFF, ShiftType.NO_SHOW]),
        )
        .all()
    )
    all_employee_ids = set(employee_totals.keys()) | {e.id for e in shift_today}

    results = []
    for emp_id in all_employee_ids:
        emp = db.query(Employee).get(emp_id)
        earned = employee_totals.get(emp_id, 0)
        guarantee_applied = earned < settings.daily_guarantee_amount
        final_payout = settings.daily_guarantee_amount if guarantee_applied else earned
        results.append({
            "employee_id": emp_id,
            "full_name": emp.full_name if emp else "?",
            "jobs_count": employee_jobs_count.get(emp_id, 0),
            "earned_raw": round(earned, 2),
            "guarantee_applied": guarantee_applied,
            "final_payout": round(final_payout, 2),
        })

    db.commit()  # сохраняем закэшированные share_amount на JobAssignment
    results.sort(key=lambda r: -r["final_payout"])
    return {"date": day, "total_revenue": round(total_revenue_day, 2), "employees": results}


def compute_weekly_payroll(db: Session, date_from: date, date_to: date) -> dict:
    totals: dict = defaultdict(lambda: {"full_name": "", "days_worked": 0, "jobs_count": 0, "total_payout": 0.0})
    total_revenue = 0.0

    d = date_from
    while d <= date_to:
        day_report = compute_daily_payroll(db, d)
        total_revenue += day_report["total_revenue"]
        for e in day_report["employees"]:
            t = totals[e["employee_id"]]
            t["full_name"] = e["full_name"]
            t["days_worked"] += 1
            t["jobs_count"] += e["jobs_count"]
            t["total_payout"] += e["final_payout"]
        d += timedelta(days=1)

    employees = [
        {"employee_id": eid, **{k: (round(v, 2) if k == "total_payout" else v) for k, v in data.items()}}
        for eid, data in totals.items()
    ]
    employees.sort(key=lambda r: -r["total_payout"])
    return {"date_from": date_from, "date_to": date_to, "total_revenue": round(total_revenue, 2), "employees": employees}
