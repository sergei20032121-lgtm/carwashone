from datetime import date, datetime, time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_staff, require_staff_read
from app.models import Booking, BookingStatus, DryCleaningOrder, WalkInOrder, AuditLog, User
from app.schemas import PaymentOrderOut, PaymentSummaryOut, PaymentUpdate

router = APIRouter(prefix="/admin/payments", tags=["Касса"])

PAYMENT_METHODS = {"cash", "card", "transfer", "certificate", "free"}
PAYMENT_STATUSES = {"unmarked", "paid", "partial", "debt", "free"}


def _payment_row(order_type: str, order) -> PaymentOrderOut:
    if order_type == "booking":
        expected = float(order.price or 0)
        order_date = order.scheduled_at
        client_name = order.client_name
        client_phone = order.client_phone
        description = order.service_name
    elif order_type == "walk_in":
        expected = float(order.amount or 0)
        order_date = datetime.combine(order.order_date, time.min)
        client_name = order.contact_name or "Клиент без записи"
        client_phone = order.client.phone if getattr(order, "client", None) else None
        description = order.service_name_raw
    else:
        expected = float(order.amount or 0)
        order_date = datetime.combine(order.order_date, time.min)
        client_name = order.phone or "Клиент химчистки"
        client_phone = order.phone
        description = order.works_description
    paid = float(order.amount_paid or 0)
    status = order.payment_status or "unmarked"
    debt = max(0, expected - paid) if status in {"debt", "partial"} else 0
    return PaymentOrderOut(
        order_type=order_type,
        order_id=order.id,
        order_date=order_date,
        client_name=client_name,
        client_phone=client_phone,
        description=description,
        expected_amount=expected,
        amount_paid=paid,
        debt_amount=debt,
        payment_method=order.payment_method,
        payment_status=status,
        payment_note=order.payment_note,
    )


@router.get("", response_model=PaymentSummaryOut, dependencies=[Depends(require_staff_read)])
def payment_summary(day: date, db: Session = Depends(get_db)):
    bookings = db.query(Booking).filter(
        Booking.scheduled_at >= datetime.combine(day, time.min),
        Booking.scheduled_at <= datetime.combine(day, time.max),
        Booking.status != BookingStatus.CANCELLED,
    ).all()
    walk_ins = db.query(WalkInOrder).filter(WalkInOrder.order_date == day).all()
    dry_orders = db.query(DryCleaningOrder).filter(DryCleaningOrder.order_date == day).all()
    rows = (
        [_payment_row("booking", order) for order in bookings]
        + [_payment_row("walk_in", order) for order in walk_ins]
        + [_payment_row("dry_cleaning", order) for order in dry_orders]
    )
    rows.sort(key=lambda row: (row.order_date, row.order_type, row.order_id))
    by_method = {key: 0.0 for key in ("cash", "card", "transfer", "certificate", "free")}
    for row in rows:
        if row.payment_method in by_method:
            by_method[row.payment_method] += row.amount_paid
    return PaymentSummaryOut(
        day=day,
        expected_total=round(sum(row.expected_amount for row in rows), 2),
        paid_total=round(sum(row.amount_paid for row in rows), 2),
        debt_total=round(sum(row.debt_amount for row in rows), 2),
        unmarked_total=round(sum(row.expected_amount for row in rows if row.payment_status == "unmarked"), 2),
        unmarked_count=sum(1 for row in rows if row.payment_status == "unmarked"),
        by_method={key: round(value, 2) for key, value in by_method.items()},
        orders=rows,
    )


@router.put("/{order_type}/{order_id}", response_model=PaymentOrderOut)
def update_payment(
    order_type: Literal["booking", "walk_in", "dry_cleaning"],
    order_id: int,
    data: PaymentUpdate,
    actor: User = Depends(require_staff),
    db: Session = Depends(get_db),
):
    model = {"booking": Booking, "walk_in": WalkInOrder, "dry_cleaning": DryCleaningOrder}[order_type]
    order = db.query(model).get(order_id)
    if not order:
        raise HTTPException(404, "Заказ не найден")
    if data.payment_status not in PAYMENT_STATUSES:
        raise HTTPException(400, "Неизвестный статус оплаты")
    if data.payment_method and data.payment_method not in PAYMENT_METHODS:
        raise HTTPException(400, "Неизвестный способ оплаты")

    expected = float(order.price or 0) if order_type == "booking" else float(order.amount or 0)
    amount_paid = float(data.amount_paid)
    method = data.payment_method
    if data.payment_status == "free":
        amount_paid, method = 0, "free"
    elif amount_paid > expected:
        raise HTTPException(400, "Полученная сумма не может быть больше суммы заказа")
    elif data.payment_status == "paid" and abs(amount_paid - expected) > 0.01:
        raise HTTPException(400, "Для статуса «Оплачено» полученная сумма должна совпадать с суммой заказа")
    elif data.payment_status == "partial" and not (0 < amount_paid < expected):
        raise HTTPException(400, "Для частичной оплаты укажите сумму больше нуля и меньше суммы заказа")
    elif amount_paid > 0 and not method:
        raise HTTPException(400, "Укажите способ оплаты")

    order.payment_method = method
    order.payment_status = data.payment_status
    order.amount_paid = amount_paid
    order.payment_note = data.payment_note
    db.add(AuditLog(
        actor_user_id=actor.id,
        action="update",
        entity=f"{order_type}_payment",
        entity_id=order.id,
        note=f"Оплата: {data.payment_status}, получено {amount_paid}",
    ))
    db.commit()
    db.refresh(order)
    return _payment_row(order_type, order)
