from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DryCleaningOrder, Service, ServiceCategory, User, AuditLog, JobAssignment, Employee
from app.schemas import DryCleaningOrderCreate, DryCleaningOrderOut, DryCleaningOrderUpdate, ServiceOut, EmployeeAssignmentSet
from app.dependencies import require_staff, require_admin
from app.excel_utils import export_drycleaning_xlsx, parse_drycleaning_xlsx

router = APIRouter(prefix="/dry-cleaning", tags=["Химчистка"])


def _attach_employee_names(db: Session, orders: List[DryCleaningOrder]) -> List[DryCleaningOrder]:
    if not orders:
        return orders
    ids = [o.id for o in orders]
    assignments = db.query(JobAssignment).filter(
        JobAssignment.order_type == "dry_cleaning", JobAssignment.order_id.in_(ids)
    ).all()
    emp_ids = {a.employee_id for a in assignments}
    employees = {e.id: e.full_name for e in db.query(Employee).filter(Employee.id.in_(emp_ids)).all()} if emp_ids else {}
    by_order: dict = {}
    for a in assignments:
        by_order.setdefault(a.order_id, []).append(employees.get(a.employee_id, "?"))
    for o in orders:
        o.assigned_employee_names = by_order.get(o.id, [])
    return orders


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
    orders = q.order_by(DryCleaningOrder.order_date.desc()).all()
    return _attach_employee_names(db, orders)


@router.post(
    "/orders",
    response_model=DryCleaningOrderOut,
    summary="Добавить заказ химчистки (админ/сотрудник)",
)
def create_order(data: DryCleaningOrderCreate, actor: User = Depends(require_staff), db: Session = Depends(get_db)):
    order = DryCleaningOrder(**data.model_dump())
    db.add(order)
    db.flush()
    db.add(AuditLog(actor_user_id=actor.id, action="create", entity="dry_cleaning_order", entity_id=order.id))
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


@router.post("/orders/import", summary="Загрузить строки из .xlsx — понимает и наш формат, и родной Химчистка.xlsx")
async def import_orders(file: UploadFile = File(...), actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    content = await file.read()
    try:
        rows = parse_drycleaning_xlsx(content)
    except Exception as e:
        raise HTTPException(400, f"Не удалось прочитать файл: {e}")

    created = 0
    for row in rows:
        db.add(DryCleaningOrder(**row))
        created += 1
    db.add(AuditLog(actor_user_id=actor.id, action="create", entity="dry_cleaning_order",
                     note=f"Импорт из файла: {created} строк"))
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


@router.put("/orders/{order_id}/employees", response_model=DryCleaningOrderOut, summary="Назначить сотрудников на заказ химчистки")
def assign_employees(order_id: int, data: EmployeeAssignmentSet, actor: User = Depends(require_staff), db: Session = Depends(get_db)):
    order = db.query(DryCleaningOrder).get(order_id)
    if not order:
        raise HTTPException(404, "Заказ не найден")

    db.query(JobAssignment).filter(JobAssignment.order_type == "dry_cleaning", JobAssignment.order_id == order_id).delete()
    for emp_id in data.employee_ids:
        if not db.query(Employee).get(emp_id):
            raise HTTPException(400, f"Сотрудник id={emp_id} не найден")
        db.add(JobAssignment(order_type="dry_cleaning", order_id=order_id, employee_id=emp_id))

    order.employee_id = data.employee_ids[0] if data.employee_ids else None

    db.add(AuditLog(actor_user_id=actor.id, action="update", entity="dry_cleaning_order", entity_id=order.id,
                     note=f"Назначены сотрудники: {data.employee_ids}"))
    db.commit()
    db.refresh(order)
    return order


@router.patch("/orders/{order_id}", response_model=DryCleaningOrderOut, summary="Изменить заказ химчистки")
def update_order(order_id: int, data: DryCleaningOrderUpdate, actor: User = Depends(require_staff), db: Session = Depends(get_db)):
    order = db.query(DryCleaningOrder).get(order_id)
    if not order:
        raise HTTPException(404, "Заказ не найден")
    changes = data.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(order, k, v)
    db.add(AuditLog(actor_user_id=actor.id, action="update", entity="dry_cleaning_order", entity_id=order.id,
                     note=f"Изменено: {', '.join(changes.keys())}"))
    db.commit()
    db.refresh(order)
    return order


@router.delete("/orders/{order_id}", summary="Удалить заказ химчистки (только админ)")
def delete_order(order_id: int, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    order = db.query(DryCleaningOrder).get(order_id)
    if not order:
        raise HTTPException(404, "Заказ не найден")
    db.add(AuditLog(actor_user_id=actor.id, action="delete", entity="dry_cleaning_order", entity_id=order.id))
    db.delete(order)
    db.commit()
    return {"detail": "Заказ удалён"}
