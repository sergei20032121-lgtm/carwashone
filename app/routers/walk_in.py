from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import WalkInOrder, Service, User, UserRole, AuditLog
from app.schemas import WalkInOrderCreate, WalkInOrderOut, WalkInOrderUpdate
from app.dependencies import require_staff, require_admin
from app.loyalty import register_wash, price_with_discount, calc_employee_payout
from app.excel_utils import export_walkin_xlsx, parse_walkin_any

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


@router.post("", response_model=WalkInOrderOut, summary="Добавить заказ (клиент без записи)")
def create_order(data: WalkInOrderCreate, actor: User = Depends(require_staff), db: Session = Depends(get_db)):
    client = None
    if data.client_phone:
        client = db.query(User).filter(User.phone == data.client_phone).first()
        if not client:
            client = User(phone=data.client_phone, full_name=data.contact_name, role=UserRole.CLIENT)
            db.add(client)
            db.flush()

    service = db.query(Service).get(data.service_id) if data.service_id else None

    order = WalkInOrder(
        order_date=data.order_date,
        time_note=data.time_note,
        service_id=data.service_id,
        service_name_raw=data.service_name_raw,
        extra_service=data.extra_service,
        car_model=data.car_model,
        amount=data.amount,
        employee_payout=calc_employee_payout(data.amount, service.payout_pct) if service else None,
        contact_name=data.contact_name,
        client_id=client.id if client else None,
        employee_id=data.employee_id,
    )
    db.add(order)
    db.flush()

    # если удалось привязать клиента и услуга помечена как "полная мойка" — ставим ананас
    if client and service:
        result = register_wash(db, client, service, walk_in_order_id=order.id)
        if result.applied:
            order.amount = price_with_discount(data.amount, result.discount_pct)
            order.employee_payout = calc_employee_payout(order.amount, service.payout_pct)

    db.add(AuditLog(actor_user_id=actor.id, action="create", entity="walk_in_order", entity_id=order.id))
    db.commit()
    db.refresh(order)
    return order


@router.patch("/{order_id}", response_model=WalkInOrderOut, summary="Изменить заказ")
def update_order(order_id: int, data: WalkInOrderUpdate, actor: User = Depends(require_staff), db: Session = Depends(get_db)):
    order = db.query(WalkInOrder).get(order_id)
    if not order:
        raise HTTPException(404, "Заказ не найден")
    changes = data.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(order, k, v)
    db.add(AuditLog(actor_user_id=actor.id, action="update", entity="walk_in_order", entity_id=order.id,
                     note=f"Изменено: {', '.join(changes.keys())}"))
    db.commit()
    db.refresh(order)
    return order


@router.delete("/{order_id}", summary="Удалить заказ (только админ)")
def delete_order(order_id: int, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    order = db.query(WalkInOrder).get(order_id)
    if not order:
        raise HTTPException(404, "Заказ не найден")
    db.add(AuditLog(actor_user_id=actor.id, action="delete", entity="walk_in_order", entity_id=order.id))
    db.delete(order)
    db.commit()
    return {"detail": "Заказ удалён"}


@router.get("/export", dependencies=[Depends(require_staff)], summary="Скачать журнал целиком как .xlsx")
def export_orders(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
):
    q = db.query(WalkInOrder)
    if date_from:
        q = q.filter(WalkInOrder.order_date >= date_from)
    if date_to:
        q = q.filter(WalkInOrder.order_date <= date_to)
    orders = q.order_by(WalkInOrder.order_date).all()
    buf = export_walkin_xlsx(orders)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=uchet-avtomoyka.xlsx"},
    )


@router.post("/import", summary="Загрузить строки из .xlsx — понимает и наш экспортный формат, и родной 'Учёт.xlsx'")
async def import_orders(file: UploadFile = File(...), actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    content = await file.read()
    try:
        rows = parse_walkin_any(content)
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать файл: {e}")

    created = 0
    for row in rows:
        db.add(WalkInOrder(**row))
        created += 1
    db.add(AuditLog(actor_user_id=actor.id, action="create", entity="walk_in_order",
                     note=f"Импорт из файла: {created} строк"))
    db.commit()
    return {"detail": f"Импортировано строк: {created}"}
