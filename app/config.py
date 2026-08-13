from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Автомойка №1"
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 60 * 24 * 30
    cors_origins: str = "http://127.0.0.1:8123,http://localhost:8123"
    business_timezone: str = "Asia/Yekaterinburg"

    database_url: str = "sqlite:///./carwash.db"

    sms_provider_api_key: str = ""
    # Оставьте пустым, пока имя отправителя не одобрено в кабинете SMS.ru.
    sms_provider_sender: str = ""
    sms_provider_timeout_seconds: float = 10.0
    # console | smsru | phone. В режиме phone сообщения забирает рабочий Android.
    sms_delivery_mode: str = "console"
    phone_gateway_token: str = ""
    phone_gateway_name: str = "redmi-7a"

    twogis_api_key: str = ""
    twogis_org_id: str = ""
    twogis_org_url: str = ""

    # ВКонтакте — токен НЕ коммитим в git, задаётся через .env / переменные окружения на сервере
    vk_group_domain: str = ""
    vk_access_token: str = ""

    admin_phone: str = "+79990000000"
    # В тестовом режиме seed каждый раз восстанавливает понятные демо-доступы.
    # На продакшене обязательно задайте TEST_MODE=false и собственные пароли.
    test_mode: bool = True
    admin_password: str = "admin"
    manager_password: str = "manager"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
