from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Employee, ShiftSchedule, AuditLog, User
from app.schemas import EmployeeOut, EmployeeCreate, EmployeeUpdate, ShiftSet, ShiftOut
from app.dependencies import require_staff_read, require_schedule_write

router = APIRouter(prefix="/schedule", tags=["График работы"])


@router.get("/employees", response_model=List[EmployeeOut], dependencies=[Depends(require_staff_read)])
def list_employees(db: Session = Depends(get_db)):
    return db.query(Employee).filter(Employee.is_active == True).all()  # noqa: E712


@router.post("/employees", response_model=EmployeeOut, dependencies=[Depends(require_schedule_write)])
def create_employee(data: EmployeeCreate, db: Session = Depends(get_db)):
    emp = Employee(**data.model_dump())
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


@router.patch("/employees/{employee_id}", response_model=EmployeeOut, summary="Изменить сотрудника (руководитель/админ)")
def update_employee(employee_id: int, data: EmployeeUpdate, actor: User = Depends(require_schedule_write), db: Session = Depends(get_db)):
    emp = db.query(Employee).get(employee_id)
    if not emp:
        raise HTTPException(404, "Сотрудник не найден")
    changes = data.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(emp, k, v)
    db.add(AuditLog(actor_user_id=actor.id, action="update", entity="employee", entity_id=emp.id,
                     note=f"Изменено: {', '.join(changes.keys())}"))
    db.commit()
    db.refresh(emp)
    return emp


@router.delete("/employees/{employee_id}", summary="Скрыть сотрудника (руководитель/админ)")
def delete_employee(employee_id: int, actor: User = Depends(require_schedule_write), db: Session = Depends(get_db)):
    emp = db.query(Employee).get(employee_id)
    if not emp:
        raise HTTPException(404, "Сотрудник не найден")
    emp.is_active = False
    db.add(AuditLog(actor_user_id=actor.id, action="delete", entity="employee", entity_id=emp.id))
    db.commit()
    return {"detail": "Сотрудник скрыт (деактивирован)"}


@router.get("", response_model=List[ShiftOut], dependencies=[Depends(require_staff_read)], summary="График за период")
def get_schedule(
    date_from: date,
    date_to: date,
    employee_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    q = db.query(ShiftSchedule).filter(
        ShiftSchedule.work_date >= date_from, ShiftSchedule.work_date <= date_to
    )
    if employee_id:
        q = q.filter(ShiftSchedule.employee_id == employee_id)
    return q.all()


@router.put("", response_model=ShiftOut, dependencies=[Depends(require_schedule_write)], summary="Проставить смену на день")
def set_shift(data: ShiftSet, db: Session = Depends(get_db)):
    shift = (
        db.query(ShiftSchedule)
        .filter(
            ShiftSchedule.employee_id == data.employee_id,
            ShiftSchedule.work_date == data.work_date,
        )
        .first()
    )
    if shift:
        shift.shift_type = data.shift_type
        shift.note = data.note
    else:
        shift = ShiftSchedule(**data.model_dump())
        db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift
