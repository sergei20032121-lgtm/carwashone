# Обновление v29 — подготовка к production

## Что добавлено

- обязательная галочка согласия перед отправкой SMS-кода;
- серверная проверка согласия и сохранение даты/версии текста;
- политика обработки персональных данных и отдельное согласие;
- production Docker Compose с базой вне Git-репозитория;
- атомарные SQLite-бэкапы, контрольная сумма и хранение 30 дней;
- ежедневный systemd-таймер резервного копирования;
- безопасное обновление `git pull --ff-only` с бэкапом до сборки;
- read-only release smoke-test сайта, API и ролей;
- HTTPS QR-код с ананасом: `frontend/static/img/qr-carwashone.png`.
- реальная отправка одноразовых кодов через SMS.ru с обработкой ошибок;
- защита SMS-баланса: повтор через 60 секунд, не более 5 запросов за 15 минут.

## Перед выкладкой

В `frontend/privacy.html` и `frontend/consent.html` заменить квадратные
скобки на реальные реквизиты оператора: наименование, ИНН и email.

На сервере проверить `.env`: `TEST_MODE=false`, уникальные пароли,
длинный `SECRET_KEY`, HTTPS-домены в `CORS_ORIGINS`.

## Проверка после выкладки

```bash
docker exec carwashone python scripts/release_smoke.py --base-url https://carwashone.ru
systemctl status carwashone-backup.timer --no-pager
```
