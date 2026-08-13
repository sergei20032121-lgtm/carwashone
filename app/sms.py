"""Отправка сервисных SMS-кодов через SMS.ru."""
import logging

import httpx

from app.config import settings
from app.database import SessionLocal
from app.models import PhoneGatewayCommand

logger = logging.getLogger("sms")
SMS_RU_SEND_URL = "https://sms.ru/sms/send"


class SMSDeliveryError(RuntimeError):
    """SMS.ru не принял сообщение или не ответил."""


def _recipient(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    return digits


def send_sms(phone: str, code: str) -> None:
    message_text = f"Код для входа в Автомойку №1: {code}"
    mode = settings.sms_delivery_mode.strip().lower()

    if mode == "phone":
        if not settings.phone_gateway_token:
            raise SMSDeliveryError("Телефонный шлюз не настроен")
        db = SessionLocal()
        try:
            db.add(PhoneGatewayCommand(
                command_type="send_sms",
                recipient=_recipient(phone),
                message=message_text,
                status="pending",
            ))
            db.commit()
        finally:
            db.close()
        logger.info("SMS для номера …%s поставлено в очередь рабочего телефона", _recipient(phone)[-4:])
        return

    if mode == "console" or not settings.sms_provider_api_key:
        # Локальный режим: без ключа код остаётся доступен в консоли разработчика.
        logger.warning("[SMS-DEV] Код для %s: %s", phone, code)
        print(f"[SMS-DEV] Код подтверждения для {phone}: {code}")
        return

    recipient = _recipient(phone)
    payload = {
        "api_id": settings.sms_provider_api_key,
        "to": recipient,
        "msg": message_text,
        "json": 1,
    }
    if settings.sms_provider_sender.strip():
        payload["from"] = settings.sms_provider_sender.strip()

    try:
        response = httpx.post(
            SMS_RU_SEND_URL,
            data=payload,
            timeout=settings.sms_provider_timeout_seconds,
        )
        response.raise_for_status()
        result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.exception("SMS.ru недоступен или вернул некорректный ответ")
        raise SMSDeliveryError("Не удалось связаться с SMS-провайдером") from exc

    if result.get("status") != "OK":
        logger.error(
            "SMS.ru отклонил запрос: code=%s text=%s",
            result.get("status_code"),
            result.get("status_text"),
        )
        raise SMSDeliveryError(result.get("status_text") or "SMS.ru отклонил запрос")

    message = (result.get("sms") or {}).get(recipient)
    if message and message.get("status") != "OK":
        logger.error(
            "SMS.ru не принял сообщение: code=%s text=%s",
            message.get("status_code"),
            message.get("status_text"),
        )
        raise SMSDeliveryError(message.get("status_text") or "SMS.ru не принял сообщение")

    logger.info("SMS.ru принял сервисное сообщение для номера …%s", recipient[-4:])
