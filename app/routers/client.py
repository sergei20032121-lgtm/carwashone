from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, CarProfile, GiftCertificate, UserRole
from app.schemas import (
    CarProfileCreate, CarProfileOut, ReferralInfo,
    BirthdayUpdate, UserOut,
    GiftCertificateCreate, GiftCertificateOut, GiftCertificateRedeem,
)
from app.dependencies import get_current_user, require_admin
from app.utils import generate_code

router = APIRouter(tags=["Клиент: машины, рефералы, сертификаты"])


# ---------------------- Профили машин ----------------------

@router.get("/cars", response_model=List[CarProfileOut], summary="Мои сохранённые машины")
def list_cars(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(CarProfile).filter(CarProfile.user_id == user.id).all()


@router.post("/cars", response_model=CarProfileOut, summary="Добавить машину")
def add_car(data: CarProfileCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    car = CarProfile(user_id=user.id, **data.model_dump())
    db.add(car)
    db.commit()
    db.refresh(car)
    return car


@router.delete("/cars/{car_id}", summary="Удалить машину")
def delete_car(car_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    car = db.query(CarProfile).filter(CarProfile.id == car_id, CarProfile.user_id == user.id).first()
    if not car:
        raise HTTPException(404, "Машина не найдена")
    db.delete(car)
    db.commit()
    return {"detail": "Удалено"}


# ---------------------- Реферальная программа ----------------------

@router.get("/referral", response_model=ReferralInfo, summary="Мой реферальный код и ссылка")
def my_referral(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.referral_code:
        # генерируем один раз при первом обращении, гарантируя уникальность
        while True:
            code = generate_code(6)
            if not db.query(User).filter(User.referral_code == code).first():
                break
        user.referral_code = code
        db.commit()

    referred_count = db.query(User).filter(User.referred_by_user_id == user.id).count()
    return ReferralInfo(
        referral_code=user.referral_code,
        referred_count=referred_count,
        referral_link=f"/site/index.html?ref={user.referral_code}",
    )


# ---------------------- День рождения ----------------------

@router.put("/me/birthday", response_model=UserOut, summary="Указать дату рождения (для бонуса в день рождения)")
def set_birthday(data: BirthdayUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.birthday = data.birthday
    db.commit()
    db.refresh(user)
    return user


# ---------------------- Подарочные сертификаты ----------------------

@router.post("/gift-certificates", response_model=GiftCertificateOut, summary="Купить подарочный сертификат")
def create_certificate(data: GiftCertificateCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    while True:
        code = "GIFT-" + generate_code(8)
        if not db.query(GiftCertificate).filter(GiftCertificate.code == code).first():
            break
    cert = GiftCertificate(code=code, amount=data.amount, issued_to_phone=data.issued_to_phone)
    db.add(cert)
    db.commit()
    db.refresh(cert)
    return cert


@router.post("/gift-certificates/redeem", response_model=GiftCertificateOut, summary="Погасить сертификат (в оплату записи)")
def redeem_certificate(data: GiftCertificateRedeem, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cert = db.query(GiftCertificate).filter(GiftCertificate.code == data.code).first()
    if not cert:
        raise HTTPException(404, "Сертификат с таким кодом не найден")
    if cert.is_used:
        raise HTTPException(400, "Сертификат уже использован")
    cert.is_used = True
    cert.used_by_user_id = user.id
    cert.used_at = datetime.utcnow()
    db.commit()
    db.refresh(cert)
    return cert


@router.get("/gift-certificates", response_model=List[GiftCertificateOut], dependencies=[Depends(require_admin)], summary="Все сертификаты (админ)")
def list_certificates(db: Session = Depends(get_db)):
    return db.query(GiftCertificate).order_by(GiftCertificate.created_at.desc()).all()
