"""Напоминания о записи по SMS: за ~2 часа до визита, один раз на запись.

Запуск:  python -m app.send_reminders
Ставится в cron каждые 15 минут (docker exec carwashone python3 -m app.send_reminders).

Использует ту же очередь, что и остальной телефонный шлюз (PhoneGatewayCommand),
поэтому реально отправляется рабочим Android-телефоном, как и все прочие SMS.
"""
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.models import Booking, BookingStatus, PhoneGatewayCommand

REMINDER_WINDOW_HOURS = 2


def _recipient(phone: str) -> str:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    return "+" + digits if digits else ""


def send_due_reminders() -> None:
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        window_end = now + timedelta(hours=REMINDER_WINDOW_HOURS)
        candidates = (
            db.query(Booking)
            .filter(
                Booking.reminder_sent_at.is_(None),
                Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED]),
                Booking.scheduled_at > now,
                Booking.scheduled_at <= window_end,
            )
            .all()
        )
        sent = 0
        for booking in candidates:
            client = booking.client
            phone = _recipient(client.phone) if client else ""
            if not phone:
                booking.reminder_sent_at = now
                continue
            service_name = booking.service.name if booking.service else "мойку"
            time_label = booking.scheduled_at.strftime("%H:%M")
            message = (
                f"Автомойка №1: напоминаем — сегодня в {time_label} вы записаны на «{service_name}». "
                f"Ждём вас на Магистральной, 90/1."
            )
            db.add(PhoneGatewayCommand(recipient=phone, message=message))
            booking.reminder_sent_at = now
            sent += 1
        db.commit()
        print(f"[reminders] проверено записей: {len(candidates)}, поставлено в очередь SMS: {sent}")
    finally:
        db.close()


if __name__ == "__main__":
    send_due_reminders()
