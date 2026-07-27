from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DryCleaningOrder, Service, ServiceCategory
from app.schemas import DryCleaningOrderCreate, DryCleaningOrderOut, DryCleaningOrderUpdate, ServiceOut
from app.dependencies import require_staff, require_admin
from app.excel_utils import export_drycleaning_xlsx, parse_drycleaning_xlsx

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


# ВАЖНО: /orders/export и /orders/import должны быть объявлены ДО /orders/{order_id},
# иначе FastAPI попытается разобрать "export"/"import" как числовой order_id и упадёт с 422.

@router.get("/orders/export", dependencies=[Depends(require_staff)], summary="Скачать журнал химчистки как .xlsx")
def export_orders(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
):
    q = db.query(DryCleaningOrder)
    if date_from:
        q = q.filter(DryCleaningOrder.order_date >= date_from)
    if date_to:
        q = q.filter(DryCleaningOrder.order_date <= date_to)
    orders = q.order_by(DryCleaningOrder.order_date).all()
    buf = export_drycleaning_xlsx(orders)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=himchistka.xlsx"},
    )


@router.post("/orders/import", dependencies=[Depends(require_admin)], summary="Загрузить строки из .xlsx (формат — как в экспорте)")
async def import_orders(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    try:
        rows = parse_drycleaning_xlsx(content)
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать файл: {e}")

    created = 0
    for row in rows:
        db.add(DryCleaningOrder(**row))
        created += 1
    db.commit()
    return {"detail": f"Импортировано строк: {created}"}


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


@router.patch("/orders/{order_id}", response_model=DryCleaningOrderOut, dependencies=[Depends(require_staff)], summary="Изменить заказ химчистки")
def update_order(order_id: int, data: DryCleaningOrderUpdate, db: Session = Depends(get_db)):
    order = db.query(DryCleaningOrder).get(order_id)
    if not order:
        raise HTTPException(404, "Заказ не найден")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(order, k, v)
    db.commit()
    db.refresh(order)
    return order


@router.delete("/orders/{order_id}", dependencies=[Depends(require_admin)], summary="Удалить заказ химчистки (только админ)")
def delete_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(DryCleaningOrder).get(order_id)
    if not order:
        raise HTTPException(404, "Заказ не найден")
    db.delete(order)
    db.commit()
    return {"detail": "Заказ удалён"}
