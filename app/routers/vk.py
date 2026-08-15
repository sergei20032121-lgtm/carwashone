import secrets
from datetime import datetime
from typing import List

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import VkSettings, VkPost, CommunicationLog, User
from app.schemas import VkSettingsOut, VkSettingsUpdate, VkPostOut, VkMessageSendIn, VkMessageOut
from app.dependencies import require_admin, require_staff
from app.config import settings

router = APIRouter(prefix="/vk", tags=["Новости ВК"])

VK_API_VERSION = "5.199"
VK_API_URL = "https://api.vk.com/method/wall.get"
VK_MESSAGES_SEND_URL = "https://api.vk.com/method/messages.send"
VK_USERS_GET_URL = "https://api.vk.com/method/users.get"


def _resolve_vk_name(db: Session, token: str, vk_user_id: int) -> str:
    cached = (
        db.query(CommunicationLog)
        .filter(CommunicationLog.channel == "vk", CommunicationLog.phone == f"vk:{vk_user_id}")
        .order_by(CommunicationLog.id.desc())
        .all()
    )
    for row in cached:
        name = (row.details or {}).get("vk_user_name")
        if name:
            return name
    if not token:
        return ""
    try:
        resp = httpx.get(VK_USERS_GET_URL, params={
            "user_ids": vk_user_id, "access_token": token, "v": VK_API_VERSION,
        }, timeout=10)
        data = resp.json()
        person = (data.get("response") or [{}])[0]
        name = f"{person.get('first_name', '')} {person.get('last_name', '')}".strip()
        return name
    except (httpx.HTTPError, ValueError, IndexError):
        return ""


def _get_or_create_settings(db: Session) -> VkSettings:
    row = db.query(VkSettings).first()
    if not row:
        # значения по умолчанию — из переменных окружения (.env), а не захардкожены в коде
        row = VkSettings(group_domain=settings.vk_group_domain, access_token=settings.vk_access_token)
        db.add(row)
        db.commit()
        db.refresh(row)
    if not row.callback_secret:
        row.callback_secret = secrets.token_hex(16)
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
    row = _get_or_create_settings(db)
    return VkSettingsOut(
        group_domain=row.group_domain,
        last_synced_at=row.last_synced_at,
        messages_token_set=bool(row.messages_access_token),
        callback_secret=row.callback_secret,
        callback_confirmation=row.callback_confirmation,
    )


@router.put("/settings", response_model=VkSettingsOut, dependencies=[Depends(require_admin)])
def update_settings(data: VkSettingsUpdate, db: Session = Depends(get_db)):
    row = _get_or_create_settings(db)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return VkSettingsOut(
        group_domain=row.group_domain,
        last_synced_at=row.last_synced_at,
        messages_token_set=bool(row.messages_access_token),
        callback_secret=row.callback_secret,
        callback_confirmation=row.callback_confirmation,
    )


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


# ---------------------------------------------------------------------------
# Сообщения сообщества (Callback API) — приём и отправка личных сообщений
# ---------------------------------------------------------------------------

@router.post("/callback", include_in_schema=False)
async def vk_callback(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    row = _get_or_create_settings(db)

    event_type = payload.get("type")

    if event_type == "confirmation":
        return PlainTextResponse(row.callback_confirmation or "")

    if row.callback_secret and payload.get("secret") != row.callback_secret:
        raise HTTPException(403, "Неверный secret")

    if event_type == "message_new":
        obj = payload.get("object", {}).get("message", {})
        vk_user_id = obj.get("from_id")
        text = obj.get("text", "")
        vk_message_id = obj.get("id")
        date_ts = obj.get("date")
        occurred = datetime.utcfromtimestamp(date_ts) if date_ts else datetime.utcnow()
        external_id = f"vk-in-{vk_message_id}" if vk_message_id else f"vk-in-{vk_user_id}-{date_ts}"
        if vk_user_id and not db.query(CommunicationLog).filter(CommunicationLog.external_id == external_id).first():
            vk_user_name = _resolve_vk_name(db, row.messages_access_token, vk_user_id)
            db.add(CommunicationLog(
                external_id=external_id, channel="vk", direction="incoming",
                phone=f"vk:{vk_user_id}", status="received", occurred_at=occurred,
                details={"text": text, "vk_user_id": vk_user_id, "vk_user_name": vk_user_name},
            ))
            db.commit()

    # VK ждёт ровно "ok" в теле ответа для любого обработанного события
    return PlainTextResponse("ok")


@router.get("/messages", response_model=List[VkMessageOut], dependencies=[Depends(require_staff)], summary="Журнал сообщений ВК")
def list_vk_messages(db: Session = Depends(get_db)):
    rows = (
        db.query(CommunicationLog)
        .filter(CommunicationLog.channel == "vk")
        .order_by(CommunicationLog.occurred_at.desc())
        .limit(300)
        .all()
    )
    result = []
    for r in rows:
        details = r.details or {}
        vk_user_id = details.get("vk_user_id")
        if vk_user_id is None and r.phone.startswith("vk:"):
            vk_user_id = int(r.phone[3:])
        result.append(VkMessageOut(
            id=r.id, direction=r.direction, vk_user_id=vk_user_id or 0,
            vk_user_name=details.get("vk_user_name") or None,
            text=details.get("text", ""), occurred_at=r.occurred_at,
        ))
    return result


@router.post("/messages/send", status_code=201, dependencies=[Depends(require_staff)], summary="Отправить сообщение клиенту ВК")
def send_vk_message(data: VkMessageSendIn, db: Session = Depends(get_db)):
    row = _get_or_create_settings(db)
    if not row.messages_access_token:
        raise HTTPException(409, "Токен для сообщений ВК не настроен (нужно отдельное право «Сообщения сообщества»)")

    try:
        resp = httpx.get(
            VK_MESSAGES_SEND_URL,
            params={
                "user_id": data.vk_user_id,
                "message": data.text,
                "random_id": secrets.randbelow(2 ** 31),
                "access_token": row.messages_access_token,
                "v": VK_API_VERSION,
            },
            timeout=15,
        )
        result = resp.json()
    except httpx.HTTPError as e:
        raise HTTPException(502, f"VK недоступен: {e}")
    except ValueError:
        raise HTTPException(502, "VK API ответил не-JSON")

    if "error" in result:
        raise HTTPException(400, f"VK отклонил отправку: {result['error'].get('error_msg', result['error'])}")

    vk_user_name = _resolve_vk_name(db, row.messages_access_token, data.vk_user_id)
    external_id = f"vk-out-{result.get('response')}-{int(datetime.utcnow().timestamp() * 1000)}"
    db.add(CommunicationLog(
        external_id=external_id, channel="vk", direction="outgoing",
        phone=f"vk:{data.vk_user_id}", status="sent", occurred_at=datetime.utcnow(),
        details={"text": data.text, "vk_user_id": data.vk_user_id, "vk_user_name": vk_user_name},
    ))
    db.commit()
    return {"ok": True}
