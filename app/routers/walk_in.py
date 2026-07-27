from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import WalkInOrder, Service, User, UserRole
from app.schemas import WalkInOrderCreate, WalkInOrderOut
from app.dependencies import require_staff
from app.loyalty import register_wash, price_with_discount

router = APIRouter(prefix="/walk-in", tags=["Журнал заказов (без записи)"])


@router.get("", response_model=List[WalkInOrderOut], dependencies=[Depends(require_staff)], summary="Список заказов за период")
def list_orders(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
):
    q = db.query(WalkInOrder)
    if date_from:
        q = q.filter(WalkInOrder.order_date >= date_from)
    if date_to:
        q = q.filter(WalkInOrder.order_date <= date_to)
    return q.order_by(WalkInOrder.order_date.desc(), WalkInOrder.id.desc()).all()


@router.post("", response_model=WalkInOrderOut, dependencies=[Depends(require_staff)], summary="Добавить заказ (клиент без записи)")
def create_order(data: WalkInOrderCreate, db: Session = Depends(get_db)):
    client = None
    if data.client_phone:
        client = db.query(User).filter(User.phone == data.client_phone).first()
        if not client:
            client = User(phone=data.client_phone, full_name=data.contact_name, role=UserRole.CLIENT)
            db.add(client)
            db.flush()

    order = WalkInOrder(
        order_date=data.order_date,
        time_note=data.time_note,
        service_id=data.service_id,
        service_name_raw=data.service_name_raw,
        extra_service=data.extra_service,
        car_model=data.car_model,
        amount=data.amount,
        contact_name=data.contact_name,
        client_id=client.id if client else None,
        employee_id=data.employee_id,
    )
    db.add(order)
    db.flush()

    # если удалось привязать клиента и услуга помечена как "полная мойка" — ставим ананас
    if client and data.service_id:
        service = db.query(Service).get(data.service_id)
        if service:
            result = register_wash(db, client, service, walk_in_order_id=order.id)
            if result.applied:
                order.amount = price_with_discount(data.amount, result.discount_pct)

    db.commit()
    db.refresh(order)
    return order
