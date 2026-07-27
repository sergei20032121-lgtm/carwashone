from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DryCleaningOrder, Service, ServiceCategory
from app.schemas import DryCleaningOrderCreate, DryCleaningOrderOut, ServiceOut
from app.dependencies import require_staff

router = APIRouter(prefix="/dry-cleaning", tags=["Химчистка"])


@router.get("/services", response_model=List[ServiceOut], summary="Прайс химчистки (публично)")
def dry_cleaning_services(db: Session = Depends(get_db)):
    return (
        db.query(Service)
        .filter(Service.category == ServiceCategory.DRY_CLEANING, Service.is_active == True)  # noqa: E712
        .order_by(Service.sort_order)
        .all()
    )


@router.get(
    "/orders",
    response_model=List[DryCleaningOrderOut],
    dependencies=[Depends(require_staff)],
    summary="Журнал заказов химчистки (админ/сотрудник)",
)
def list_orders(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
):
    q = db.query(DryCleaningOrder)
    if date_from:
        q = q.filter(DryCleaningOrder.order_date >= date_from)
    if date_to:
        q = q.filter(DryCleaningOrder.order_date <= date_to)
    return q.order_by(DryCleaningOrder.order_date.desc()).all()


@router.post(
    "/orders",
    response_model=DryCleaningOrderOut,
    dependencies=[Depends(require_staff)],
    summary="Добавить заказ химчистки (админ/сотрудник)",
)
def create_order(data: DryCleaningOrderCreate, db: Session = Depends(get_db)):
    order = DryCleaningOrder(**data.model_dump())
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@router.get(
    "/orders/{order_id}",
    response_model=DryCleaningOrderOut,
    dependencies=[Depends(require_staff)],
)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(DryCleaningOrder).get(order_id)
    if not order:
        raise HTTPException(404, "Заказ не найден")
    return order
