from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Автомойка №1"
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 60 * 24 * 30
    cors_origins: str = "http://127.0.0.1:8123,http://localhost:8123"
    business_timezone: str = "Asia/Yekaterinburg"

    database_url: str = "sqlite:///./carwash.db"

    sms_provider_api_key: str = ""
    sms_provider_sender: str = "AVTOMOYKA1"

    twogis_api_key: str = ""
    twogis_org_id: str = ""
    twogis_org_url: str = ""

    # ВКонтакте — токен НЕ коммитим в git, задаётся через .env / переменные окружения на сервере
    vk_group_domain: str = ""
    vk_access_token: str = ""

    admin_phone: str = "+79990000000"
    admin_password: str = "change-me"
    manager_password: str = "change-me"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
