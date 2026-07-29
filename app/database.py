from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def ensure_compatible_schema():
    """Добавляет новые необязательные CRM-поля в существующую БД без пересоздания таблиц."""
    additions = {
        "bookings": {
            "payment_method": "VARCHAR(20)",
            "payment_status": "VARCHAR(20) DEFAULT 'unmarked'",
            "amount_paid": "FLOAT DEFAULT 0",
            "payment_note": "VARCHAR(255)",
        },
        "walk_in_orders": {
            "payment_method": "VARCHAR(20)",
            "payment_status": "VARCHAR(20) DEFAULT 'unmarked'",
            "amount_paid": "FLOAT DEFAULT 0",
            "payment_note": "VARCHAR(255)",
        },
        "dry_cleaning_orders": {
            "payment_method": "VARCHAR(20)",
            "payment_status": "VARCHAR(20) DEFAULT 'unmarked'",
            "amount_paid": "FLOAT DEFAULT 0",
            "payment_note": "VARCHAR(255)",
        },
    }
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table_name, columns in additions.items():
            if table_name not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, ddl in columns.items():
                if column_name not in existing_columns:
                    connection.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {ddl}'))

if settings.database_url.startswith("sqlite"):
    import os
    print(f"[DB] Используется файл: {os.path.abspath(settings.database_url.replace('sqlite:///', ''))}")


def get_db():
    """Dependency: одна сессия БД на один запрос."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
