from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

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
