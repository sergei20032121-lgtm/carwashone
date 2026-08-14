"""Публичный прайс детейлинга и восстановления — отдельное направление от химчистки."""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Service, ServiceCategory
from app.schemas import ServiceOut

router = APIRouter(prefix="/detailing", tags=["Детейлинг"])


@router.get("/services", response_model=List[ServiceOut], summary="Прайс детейлинга и восстановления (публично)")
def detailing_services(db: Session = Depends(get_db)):
    return (
        db.query(Service)
        .filter(Service.category == ServiceCategory.DETAILING, Service.is_active == True)  # noqa: E712
        .order_by(Service.sort_order)
        .all()
    )
