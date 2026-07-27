"""
Отправка смс с кодом подтверждения.

Пока реальный провайдер не подключён — код просто логируется в консоль сервера,
чтобы можно было тестировать вход/запись по телефону без реальной смс.

Когда появится провайдер (SMS.ru, SMSC.ru, Green SMS и т.п.), нужно:
1. Добавить его ключ в .env (SMS_PROVIDER_API_KEY)
2. Реализовать send_sms() ниже реальным HTTP-запросом к провайдеру
"""
import logging

from app.config import settings

logger = logging.getLogger("sms")


def send_sms(phone: str, code: str) -> None:
    if not settings.sms_provider_api_key:
        # Провайдер не подключён — выводим в консоль (режим разработки)
        logger.warning("[SMS-DEV] Код для %s: %s", phone, code)
        print(f"[SMS-DEV] Код подтверждения для {phone}: {code}")
        return

    # TODO: реальный вызов API смс-провайдера, например:
    # httpx.post("https://smsc.ru/sys/send.php", params={...})
    logger.info("Отправка смс на %s (провайдер подключён, заглушка)", phone)
