from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import GisSettings, GisReview
from app.schemas import GisSettingsOut, GisSettingsUpdate, GisReviewOut
from app.dependencies import require_admin

router = APIRouter(prefix="/reviews", tags=["Отзывы 2ГИС"])


def _get_or_create_settings(db: Session) -> GisSettings:
    settings_row = db.query(GisSettings).first()
    if not settings_row:
        settings_row = GisSettings()
        db.add(settings_row)
        db.commit()
        db.refresh(settings_row)
    return settings_row


@router.get("", response_model=List[GisReviewOut], summary="Отзывы (публично, кэш из 2ГИС)")
def list_reviews(db: Session = Depends(get_db)):
    return db.query(GisReview).order_by(GisReview.published_at.desc()).limit(20).all()


@router.get("/summary", response_model=GisSettingsOut, summary="Рейтинг и ссылка на филиал 2ГИС")
def summary(db: Session = Depends(get_db)):
    return _get_or_create_settings(db)


@router.put("/settings", response_model=GisSettingsOut, dependencies=[Depends(require_admin)])
def update_settings(data: GisSettingsUpdate, db: Session = Depends(get_db)):
    settings_row = _get_or_create_settings(db)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(settings_row, k, v)
    db.commit()
    db.refresh(settings_row)
    return settings_row


@router.post("/sync", dependencies=[Depends(require_admin)], summary="Подтянуть свежие отзывы с 2ГИС")
def sync_reviews(db: Session = Depends(get_db)):
    settings_row = _get_or_create_settings(db)
    if not settings_row.org_id and not settings_row.org_url:
        raise HTTPException(
            400,
            "Сначала укажите org_id / ссылку филиала через PUT /reviews/settings — "
            "как только пришлёшь ссылку на 2ГИС, здесь будет реальный запрос к их API.",
        )
    # TODO: реальный запрос к 2ГИС Catalog API (нужен API-ключ партнёра):
    #   GET https://catalog.api.2gis.com/3.0/items/{org_id}/reviews?key=...
    # Пока — просто отмечаем время последней попытки синка.
    settings_row.last_synced_at = datetime.utcnow()
    db.commit()
    return {"detail": "Заглушка: подключим реальный запрос, когда пришлёшь ссылку/ключ 2ГИС"}
