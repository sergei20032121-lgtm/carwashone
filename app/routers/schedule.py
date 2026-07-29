from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from datetime import timedelta

from app.models import Employee, ShiftSchedule, ShiftType, AuditLog, User
from app.schemas import (
    EmployeeOut, EmployeeCreate, EmployeeUpdate, ShiftSet, ShiftOut,
    ShiftBulkSet, AdminOnDutySet,
)
from app.dependencies import require_staff_read, require_schedule_write

router = APIRouter(prefix="/schedule", tags=["График работы"])
ADMIN_DUTY_MARKER = "[ADMIN_ON_DUTY]"


def _set_admin_marker(note: Optional[str], enabled: bool) -> Optional[str]:
    clean = (note or "").replace(ADMIN_DUTY_MARKER, "").strip()
    if enabled:
        return f"{ADMIN_DUTY_MARKER} {clean}".strip()
    return clean or None


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
        if data.note is not None:
            shift.note = data.note
    else:
        shift = ShiftSchedule(**data.model_dump())
        db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift


@router.put("/bulk", response_model=List[ShiftOut], summary="Массово проставить смены")
def set_shifts_bulk(
    data: ShiftBulkSet,
    actor: User = Depends(require_schedule_write),
    db: Session = Depends(get_db),
):
    if data.date_to < data.date_from:
        raise HTTPException(400, "Дата окончания не может быть раньше даты начала")
    if (data.date_to - data.date_from).days > 62:
        raise HTTPException(400, "За один раз можно заполнить не больше 63 дней")
    employees = db.query(Employee).filter(
        Employee.id.in_(data.employee_ids),
        Employee.is_active == True,  # noqa: E712
    ).all()
    if len(employees) != len(set(data.employee_ids)):
        raise HTTPException(400, "Один или несколько сотрудников не найдены")

    result = []
    day = data.date_from
    while day <= data.date_to:
        for employee in employees:
            shift = db.query(ShiftSchedule).filter(
                ShiftSchedule.employee_id == employee.id,
                ShiftSchedule.work_date == day,
            ).first()
            if shift:
                shift.shift_type = data.shift_type
            else:
                shift = ShiftSchedule(
                    employee_id=employee.id,
                    work_date=day,
                    shift_type=data.shift_type,
                )
                db.add(shift)
            result.append(shift)
        day += timedelta(days=1)
    db.add(AuditLog(
        actor_user_id=actor.id,
        action="update",
        entity="schedule",
        note=f"Массовая смена {data.date_from}—{data.date_to}: {len(employees)} сотрудников",
    ))
    db.commit()
    for shift in result:
        db.refresh(shift)
    return result


@router.put("/admin-on-duty", response_model=ShiftOut, summary="Выбрать администратора смены")
def set_admin_on_duty(
    data: AdminOnDutySet,
    actor: User = Depends(require_schedule_write),
    db: Session = Depends(get_db),
):
    employee = db.query(Employee).filter(
        Employee.id == data.employee_id,
        Employee.is_active == True,  # noqa: E712
    ).first()
    if not employee:
        raise HTTPException(404, "Сотрудник не найден")
    if not employee.is_admin_role:
        raise HTTPException(400, "У сотрудника нет допуска администратора смены")

    shifts = db.query(ShiftSchedule).filter(ShiftSchedule.work_date == data.work_date).all()
    for shift in shifts:
        shift.note = _set_admin_marker(shift.note, False)

    selected = next((shift for shift in shifts if shift.employee_id == employee.id), None)
    if not selected:
        selected = ShiftSchedule(
            employee_id=employee.id,
            work_date=data.work_date,
            shift_type=ShiftType.FULL_DAY,
        )
        db.add(selected)
    elif selected.shift_type in (ShiftType.DAY_OFF, ShiftType.NO_SHOW):
        selected.shift_type = ShiftType.FULL_DAY
    selected.note = _set_admin_marker(selected.note, True)
    db.add(AuditLog(
        actor_user_id=actor.id,
        action="update",
        entity="schedule",
        entity_id=employee.id,
        note=f"Администратор смены на {data.work_date}: {employee.full_name}",
    ))
    db.commit()
    db.refresh(selected)
    return selected
