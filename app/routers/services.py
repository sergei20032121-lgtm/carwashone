from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Service, ServiceCategory
from app.schemas import ServiceOut, ServiceCreate
from app.dependencies import require_admin

router = APIRouter(prefix="/services", tags=["Услуги"])


@router.get("", response_model=List[ServiceOut], summary="Список услуг (мойка)")
def list_services(
    category: Optional[ServiceCategory] = ServiceCategory.WASH,
    db: Session = Depends(get_db),
):
    q = db.query(Service).filter(Service.is_active == True)  # noqa: E712
    if category:
        q = q.filter(Service.category == category)
    return q.order_by(Service.sort_order).all()


@router.get("/{service_id}", response_model=ServiceOut)
def get_service(service_id: int, db: Session = Depends(get_db)):
    service = db.query(Service).get(service_id)
    if not service:
        raise HTTPException(404, "Услуга не найдена")
    return service


@router.post("", response_model=ServiceOut, dependencies=[Depends(require_admin)], summary="Создать услугу (админ)")
def create_service(data: ServiceCreate, db: Session = Depends(get_db)):
    service = Service(**data.model_dump())
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@router.patch("/{service_id}", response_model=ServiceOut, dependencies=[Depends(require_admin)])
def update_service(service_id: int, data: ServiceCreate, db: Session = Depends(get_db)):
    service = db.query(Service).get(service_id)
    if not service:
        raise HTTPException(404, "Услуга не найдена")
    for k, v in data.model_dump().items():
        setattr(service, k, v)
    db.commit()
    db.refresh(service)
    return service


@router.delete("/{service_id}", dependencies=[Depends(require_admin)])
def delete_service(service_id: int, db: Session = Depends(get_db)):
    service = db.query(Service).get(service_id)
    if not service:
        raise HTTPException(404, "Услуга не найдена")
    service.is_active = False
    db.commit()
    return {"detail": "Услуга скрыта"}
