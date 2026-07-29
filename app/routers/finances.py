from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin, require_staff, require_staff_read
from app.models import AuditLog, DayClosure, Expense, User
from app.routers.payments import payment_summary
from app.schemas import (
    DayClosureOut,
    DayClosureUpdate,
    ExpenseCreate,
    ExpenseOut,
    FinanceDayOut,
)

router = APIRouter(prefix="/admin/finances", tags=["Финансы смены"])

METHODS = {"cash", "card", "transfer", "certificate"}


def _expense_out(expense: Expense) -> ExpenseOut:
    return ExpenseOut(
        id=expense.id,
        expense_date=expense.expense_date,
        category=expense.category,
        description=expense.description,
        amount=float(expense.amount),
        payment_method=expense.payment_method,
        created_by_name=expense.created_by.full_name if expense.created_by else None,
        created_at=expense.created_at,
    )


def _closure_out(closure: DayClosure, expected: dict[str, float]) -> DayClosureOut:
    counted_total = closure.counted_cash + closure.counted_card + closure.counted_transfer
    expected_total = expected["cash"] + expected["card"] + expected["transfer"]
    return DayClosureOut(
        closure_date=closure.closure_date,
        counted_cash=closure.counted_cash,
        counted_card=closure.counted_card,
        counted_transfer=closure.counted_transfer,
        counted_total=round(counted_total, 2),
        variance_cash=round(closure.counted_cash - expected["cash"], 2),
        variance_card=round(closure.counted_card - expected["card"], 2),
        variance_transfer=round(closure.counted_transfer - expected["transfer"], 2),
        variance_total=round(counted_total - expected_total, 2),
        note=closure.note,
        closed_by_name=closure.closed_by.full_name if closure.closed_by else None,
        closed_at=closure.closed_at,
    )


@router.get("/day", response_model=FinanceDayOut, dependencies=[Depends(require_staff_read)])
def finance_day(day: date, db: Session = Depends(get_db)):
    payments = payment_summary(day=day, db=db)
    expenses = db.query(Expense).filter(Expense.expense_date == day).order_by(Expense.created_at.desc()).all()
    closure = db.query(DayClosure).filter(DayClosure.closure_date == day).first()
    expenses_total = round(sum(float(item.amount) for item in expenses), 2)
    expense_by_method = {
        key: sum(float(item.amount) for item in expenses if item.payment_method == key)
        for key in ("cash", "card", "transfer")
    }
    expected = {
        key: round(float(payments.by_method.get(key, 0)) - expense_by_method[key], 2)
        for key in ("cash", "card", "transfer")
    }
    return FinanceDayOut(
        day=day,
        received_total=payments.paid_total,
        expenses_total=expenses_total,
        net_total=round(payments.paid_total - expenses_total, 2),
        expected_by_method=expected,
        expenses=[_expense_out(item) for item in expenses],
        closure=_closure_out(closure, expected) if closure else None,
    )


@router.post("/expenses", response_model=ExpenseOut)
def create_expense(data: ExpenseCreate, actor: User = Depends(require_staff), db: Session = Depends(get_db)):
    if data.payment_method not in METHODS:
        raise HTTPException(400, "Неизвестный способ оплаты расхода")
    expense = Expense(**data.model_dump(), created_by_user_id=actor.id)
    db.add(expense)
    db.flush()
    db.add(AuditLog(
        actor_user_id=actor.id,
        action="create",
        entity="expense",
        entity_id=expense.id,
        note=f"{data.category}: {data.amount:.2f} ₽",
    ))
    db.commit()
    db.refresh(expense)
    return _expense_out(expense)


@router.delete("/expenses/{expense_id}")
def delete_expense(expense_id: int, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    expense = db.query(Expense).get(expense_id)
    if not expense:
        raise HTTPException(404, "Расход не найден")
    db.add(AuditLog(
        actor_user_id=actor.id,
        action="delete",
        entity="expense",
        entity_id=expense.id,
        note=f"{expense.category}: {expense.amount:.2f} ₽",
    ))
    db.delete(expense)
    db.commit()
    return {"detail": "Расход удалён"}


@router.put("/day/{day}/close", response_model=DayClosureOut)
def close_day(
    day: date,
    data: DayClosureUpdate,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    payments = payment_summary(day=day, db=db)
    expenses = db.query(Expense).filter(Expense.expense_date == day).all()
    expected = {
        key: round(
            float(payments.by_method.get(key, 0))
            - sum(float(item.amount) for item in expenses if item.payment_method == key),
            2,
        )
        for key in ("cash", "card", "transfer")
    }
    closure = db.query(DayClosure).filter(DayClosure.closure_date == day).first()
    if not closure:
        closure = DayClosure(closure_date=day)
        db.add(closure)
    for key, value in data.model_dump().items():
        setattr(closure, key, value)
    closure.closed_by_user_id = actor.id
    closure.closed_at = datetime.utcnow()
    db.flush()
    db.add(AuditLog(
        actor_user_id=actor.id,
        action="update",
        entity="day_closure",
        entity_id=closure.id,
        note=f"Закрыта смена {day.isoformat()}",
    ))
    db.commit()
    db.refresh(closure)
    return _closure_out(closure, expected)
