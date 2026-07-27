from datetime import datetime
from typing import List

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import VkSettings, VkPost
from app.schemas import VkSettingsOut, VkSettingsUpdate, VkPostOut
from app.dependencies import require_admin
from app.config import settings

router = APIRouter(prefix="/vk", tags=["Новости ВК"])

VK_API_VERSION = "5.199"
VK_API_URL = "https://api.vk.com/method/wall.get"


def _get_or_create_settings(db: Session) -> VkSettings:
    row = db.query(VkSettings).first()
    if not row:
        # значения по умолчанию — из переменных окружения (.env), а не захардкожены в коде
        row = VkSettings(group_domain=settings.vk_group_domain, access_token=settings.vk_access_token)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.get("/posts", response_model=List[VkPostOut], summary="Новости (публично, кэш со стены группы)")
def list_posts(db: Session = Depends(get_db)):
    return (
        db.query(VkPost)
        .order_by(VkPost.is_pinned.desc(), VkPost.published_at.desc())
        .limit(12)
        .all()
    )


@router.get("/settings", response_model=VkSettingsOut, dependencies=[Depends(require_admin)])
def get_settings(db: Session = Depends(get_db)):
    return _get_or_create_settings(db)


@router.put("/settings", response_model=VkSettingsOut, dependencies=[Depends(require_admin)])
def update_settings(data: VkSettingsUpdate, db: Session = Depends(get_db)):
    row = _get_or_create_settings(db)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.post("/sync", dependencies=[Depends(require_admin)], summary="Подтянуть свежие посты со стены группы ВК")
def sync_posts(db: Session = Depends(get_db)):
    row = _get_or_create_settings(db)
    if not row.group_domain or not row.access_token:
        raise HTTPException(
            400,
            "Сначала укажи домен группы и access_token через PUT /vk/settings "
            "(домен — это часть после vk.com/, например carwash_one_zkm).",
        )

    try:
        resp = httpx.get(
            VK_API_URL,
            params={
                "domain": row.group_domain,
                "count": 20,
                "filter": "owner",
                "access_token": row.access_token,
                "v": VK_API_VERSION,
            },
            timeout=15,
        )
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Не удалось достучаться до VK API: {e}")

    try:
        data = resp.json()
    except ValueError:
        raise HTTPException(
            502,
            f"VK API ответил не-JSON (код {resp.status_code}). "
            f"Возможно, сеть сервера блокирует api.vk.com, либо VK временно недоступен. "
            f"Начало ответа: {resp.text[:200]!r}",
        )

    if "error" in data:
        err = data["error"]
        raise HTTPException(400, f"VK API вернул ошибку: {err.get('error_msg', err)}")

    items = data.get("response", {}).get("items", [])
    saved = 0
    for item in items:
        photo_urls = []
        for att in item.get("attachments", []):
            if att.get("type") == "photo":
                sizes = att["photo"].get("sizes", [])
                if sizes:
                    # берём самый крупный вариант фото
                    biggest = max(sizes, key=lambda s: s.get("width", 0))
                    photo_urls.append(biggest["url"])

        post = db.query(VkPost).filter(VkPost.vk_post_id == item["id"]).first()
        if not post:
            post = VkPost(vk_post_id=item["id"])
            db.add(post)

        post.text = item.get("text", "")
        post.photo_urls = photo_urls
        post.likes = item.get("likes", {}).get("count", 0)
        post.published_at = datetime.utcfromtimestamp(item["date"])
        post.is_pinned = bool(item.get("is_pinned", False))
        post.fetched_at = datetime.utcnow()
        saved += 1

    row.last_synced_at = datetime.utcnow()
    db.commit()
    return {"detail": f"Синхронизировано постов: {saved}"}
