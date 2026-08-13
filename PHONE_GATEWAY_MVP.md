# Телефонный шлюз — MVP для Redmi 7A

CRM уже умеет ставить SMS в очередь и принимать журнал звонков. Сам Android-клиент
будет отдельным APK и не меняет запуск сайта/CRM.

## Включение на сервере

```env
SMS_DELIVERY_MODE=phone
PHONE_GATEWAY_TOKEN=<результат команды openssl rand -hex 32>
PHONE_GATEWAY_NAME=redmi-7a
```

После изменения `.env` пересоберите контейнер. SMS.ru можно вернуть одной строкой:
`SMS_DELIVERY_MODE=smsru`.

## Протокол телефона

- `GET /phone-gateway/health`
- `GET /phone-gateway/commands/next`
- `POST /phone-gateway/commands/{id}/status`
- `POST /phone-gateway/calls/batch`

Во всех запросах телефона обязателен заголовок:

```text
X-Phone-Gateway-Token: <секрет>
```

Администратор читает журнал через `GET /phone-gateway/logs` с обычным CRM JWT.

## Что ещё требуется для APK

1. Экран настройки: `https://carwashone.ru`, секрет, имя устройства.
2. Foreground Service с видимым постоянным уведомлением.
3. Получение SMS-команды, отправка через `SmsManager`, отчёт `sent/failed/delivered`.
4. Чтение новых записей `CallLog.Calls` и пакетная синхронизация.
5. Автозапуск после перезагрузки и исключение приложения из энергосбережения MIUI.

Redmi 7A нужно тестировать отдельно на определение SIM: наличие номера линии в
`CallLog` зависит от прошивки и оператора. До теста это гарантировать нельзя.
