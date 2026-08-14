"""Обмен CRM с рабочим Android-телефоном: очередь SMS и журнал звонков."""
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import require_staff
from app.models import CommunicationLog, PhoneGatewayCommand, PhoneGatewayDevice, User

router = APIRouter(prefix="/phone-gateway", tags=["Телефонный шлюз"])


def _device_auth(x_phone_gateway_token: str = Header(default=""), db: Session = Depends(get_db)) -> None:
    expected = settings.phone_gateway_token
    if not expected or x_phone_gateway_token != expected:
        raise HTTPException(401, "Неверный токен телефонного шлюза")
    row = db.query(PhoneGatewayDevice).first()
    if not row:
        row = PhoneGatewayDevice()
        db.add(row)
    row.device_name = settings.phone_gateway_name
    row.last_seen_at = datetime.utcnow()
    db.commit()


DEVICE_ONLINE_THRESHOLD_MINUTES = 5


class SmsStatusIn(BaseModel):
    status: Literal["sent", "delivered", "failed"]
    error: str | None = Field(default=None, max_length=255)
    occurred_at: datetime | None = None
    line_label: str | None = Field(default=None, max_length=80)


class CallEventIn(BaseModel):
    external_id: str = Field(min_length=1, max_length=120)
    direction: Literal["incoming", "outgoing"]
    phone: str = Field(min_length=3, max_length=20)
    status: Literal["answered", "missed", "rejected", "blocked", "outgoing"]
    occurred_at: datetime
    duration_seconds: int | None = Field(default=None, ge=0)
    line_label: str | None = Field(default=None, max_length=80)
    details: dict = Field(default_factory=dict)


class CallBatchIn(BaseModel):
    events: list[CallEventIn] = Field(max_length=250)


class MessageCreateIn(BaseModel):
    phone: str = Field(min_length=5, max_length=20)
    message: str = Field(min_length=1, max_length=500)


class HandledIn(BaseModel):
    handled: bool = True
    note: str | None = Field(default=None, max_length=500)


def _phone_tail(phone: str) -> str:
    return "".join(char for char in phone if char.isdigit())[-10:]


def _client_for_phone(db: Session, phone: str) -> User | None:
    tail = _phone_tail(phone)
    if len(tail) < 10:
        return None
    return (
        db.query(User)
        .filter(func.replace(func.replace(func.replace(func.replace(func.replace(
            User.phone, "+", ""), " ", ""), "-", ""), "(", ""), ")", "").like(f"%{tail}"))
        .order_by(User.id.desc())
        .first()
    )


@router.get("/commands/next", dependencies=[Depends(_device_auth)])
def next_command(db: Session = Depends(get_db)):
    # Потерянная после сбоя команда через 2 минуты снова становится доступной.
    stale_before = datetime.utcnow() - timedelta(minutes=2)
    row = (
        db.query(PhoneGatewayCommand)
        .filter(
            PhoneGatewayCommand.command_type == "send_sms",
            (
                (PhoneGatewayCommand.status == "pending")
                | ((PhoneGatewayCommand.status == "claimed") & (PhoneGatewayCommand.claimed_at < stale_before))
            ),
        )
        .order_by(PhoneGatewayCommand.created_at.asc())
        .first()
    )
    if not row:
        return {"command": None}
    row.status = "claimed"
    row.claimed_at = datetime.utcnow()
    row.attempts = (row.attempts or 0) + 1
    row.device_name = settings.phone_gateway_name
    db.commit()
    return {"command": {"id": row.id, "type": row.command_type, "recipient": row.recipient, "message": row.message}}


@router.post("/commands/{command_id}/status", dependencies=[Depends(_device_auth)])
def command_status(command_id: int, data: SmsStatusIn, db: Session = Depends(get_db)):
    row = db.query(PhoneGatewayCommand).filter(PhoneGatewayCommand.id == command_id).first()
    if not row:
        raise HTTPException(404, "Команда не найдена")
    if row.status in {"delivered", "failed"} and row.status != data.status:
        raise HTTPException(409, "Команда уже завершена")
    row.status = data.status
    row.error = data.error
    if data.status in {"delivered", "failed"}:
        row.completed_at = datetime.utcnow()

    external_id = f"sms-command-{row.id}-{data.status}"
    if not db.query(CommunicationLog).filter(CommunicationLog.external_id == external_id).first():
        occurred = data.occurred_at or datetime.now(timezone.utc)
        if occurred.tzinfo:
            occurred = occurred.astimezone(timezone.utc).replace(tzinfo=None)
        db.add(CommunicationLog(
            external_id=external_id, channel="sms", direction="outgoing",
            phone=row.recipient, status=data.status, occurred_at=occurred,
            line_label=data.line_label, device_name=settings.phone_gateway_name,
            command_id=row.id, details={"error": data.error} if data.error else {},
        ))
    db.commit()
    return {"ok": True}


@router.post("/calls/batch", dependencies=[Depends(_device_auth)])
def calls_batch(data: CallBatchIn, db: Session = Depends(get_db)):
    inserted = 0
    for event in data.events:
        if db.query(CommunicationLog).filter(CommunicationLog.external_id == event.external_id).first():
            continue
        occurred = event.occurred_at
        if occurred.tzinfo:
            occurred = occurred.astimezone(timezone.utc).replace(tzinfo=None)
        db.add(CommunicationLog(
            external_id=event.external_id, channel="call", direction=event.direction,
            phone=event.phone, status=event.status, occurred_at=occurred,
            duration_seconds=event.duration_seconds, line_label=event.line_label,
            device_name=settings.phone_gateway_name, details=event.details,
        ))
        inserted += 1
    db.commit()
    return {"ok": True, "inserted": inserted}


@router.get("/health", dependencies=[Depends(_device_auth)])
def gateway_health():
    return {"ok": True, "server_time": datetime.now(timezone.utc)}


@router.get("/device-status")
def device_status(
    db: Session = Depends(get_db),
    _user: User = Depends(require_staff),
):
    row = db.query(PhoneGatewayDevice).first()
    if not row or not row.last_seen_at:
        return {"device_name": settings.phone_gateway_name, "last_seen_at": None, "online": False}
    online = datetime.utcnow() - row.last_seen_at < timedelta(minutes=DEVICE_ONLINE_THRESHOLD_MINUTES)
    return {"device_name": row.device_name, "last_seen_at": row.last_seen_at, "online": online}


@router.get("/logs/summary")
def communication_summary(
    db: Session = Depends(get_db),
    _user: User = Depends(require_staff),
):
    pending = db.query(CommunicationLog).filter(
        CommunicationLog.channel == "call",
        CommunicationLog.status.in_(["missed", "rejected"]),
        CommunicationLog.handled_at.is_(None),
    ).count()
    today = datetime.utcnow().date()
    calls_today = db.query(CommunicationLog).filter(
        CommunicationLog.channel == "call",
        func.date(CommunicationLog.occurred_at) == today.isoformat(),
    ).count()
    return {"pending_missed": pending, "calls_today": calls_today}


@router.post("/messages", status_code=201)
def create_message(
    data: MessageCreateIn,
    db: Session = Depends(get_db),
    _user: User = Depends(require_staff),
):
    if not settings.phone_gateway_token:
        raise HTTPException(409, "Телефонный шлюз не настроен")
    digits = "".join(char for char in data.phone if char.isdigit())
    if len(digits) < 10:
        raise HTTPException(422, "Проверьте номер телефона")
    recipient = "+" + digits if data.phone.strip().startswith("+") else digits
    row = PhoneGatewayCommand(recipient=recipient, message=data.message.strip())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "status": row.status, "recipient": row.recipient}


@router.patch("/logs/{log_id}/handled")
def set_log_handled(
    log_id: int,
    data: HandledIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
):
    row = db.query(CommunicationLog).filter(CommunicationLog.id == log_id).first()
    if not row:
        raise HTTPException(404, "Событие не найдено")
    row.handled_at = datetime.utcnow() if data.handled else None
    row.handled_by_user_id = user.id if data.handled else None
    row.handling_note = data.note.strip() if data.note else None
    db.commit()
    return {"ok": True, "handled": bool(row.handled_at)}


@router.get("/logs")
def communication_logs(
    limit: int = Query(default=100, ge=1, le=500),
    channel: str | None = Query(default=None, pattern="^(call|sms)$"),
    status: str | None = Query(default=None, max_length=30),
    query: str | None = Query(default=None, max_length=80),
    pending_only: bool = False,
    db: Session = Depends(get_db),
    _user: User = Depends(require_staff),
):
    logs_query = db.query(CommunicationLog)
    if channel:
        logs_query = logs_query.filter(CommunicationLog.channel == channel)
    if status:
        logs_query = logs_query.filter(CommunicationLog.status == status)
    if pending_only:
        logs_query = logs_query.filter(
            CommunicationLog.channel == "call",
            CommunicationLog.status.in_(["missed", "rejected"]),
            CommunicationLog.handled_at.is_(None),
        )
    if query:
        search = f"%{query.strip()}%"
        logs_query = logs_query.filter(or_(CommunicationLog.phone.like(search), CommunicationLog.line_label.like(search)))
    rows = logs_query.order_by(CommunicationLog.occurred_at.desc()).limit(limit).all()
    handlers = {user.id: user for user in db.query(User).filter(User.id.in_({row.handled_by_user_id for row in rows if row.handled_by_user_id})).all()}
    result = []
    for row in rows:
        client = _client_for_phone(db, row.phone)
        handler = handlers.get(row.handled_by_user_id)
        result.append({
        "id": row.id, "channel": row.channel, "direction": row.direction,
        "phone": row.phone, "status": row.status, "occurred_at": row.occurred_at,
        "duration_seconds": row.duration_seconds, "line_label": row.line_label,
        "device_name": row.device_name, "details": row.details or {},
        "handled_at": row.handled_at, "handling_note": row.handling_note,
        "handled_by": handler.full_name or handler.username if handler else None,
        "client": {"id": client.id, "name": client.full_name or "Клиент", "phone": client.phone} if client else None,
        })
    return result
