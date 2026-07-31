from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole, OTPCode
from app.schemas import OTPRequest, OTPVerify, StaffLogin, SetPassword, Token, UserOut
from app.security import generate_otp_code, create_access_token, verify_password, hash_password
from app.sms import SMSDeliveryError, send_sms
from app.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Авторизация"])

OTP_TTL_MINUTES = 5
OTP_RESEND_SECONDS = 60
OTP_MAX_REQUESTS_PER_15_MIN = 5


@router.post("/otp/request", summary="Запросить смс-код для входа/записи по телефону")
def request_otp(data: OTPRequest, db: Session = Depends(get_db)):
    now = datetime.utcnow()
    recent = (
        db.query(OTPCode)
        .filter(
            OTPCode.phone == data.phone,
            OTPCode.created_at >= now - timedelta(minutes=15),
        )
        .order_by(OTPCode.created_at.desc())
        .all()
    )
    if recent and (now - recent[0].created_at).total_seconds() < OTP_RESEND_SECONDS:
        wait_for = OTP_RESEND_SECONDS - int((now - recent[0].created_at).total_seconds())
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Новый код можно запросить через {wait_for} сек.",
        )
    if len(recent) >= OTP_MAX_REQUESTS_PER_15_MIN:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Слишком много запросов кода. Попробуйте через 15 минут.",
        )

    code = generate_otp_code()
    otp = OTPCode(
        phone=data.phone,
        code=code,
        expires_at=now + timedelta(minutes=OTP_TTL_MINUTES),
        consent_at=now,
        consent_policy_version=data.policy_version,
    )
    try:
        send_sms(data.phone, code)
        db.add(otp)
        db.commit()
    except SMSDeliveryError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Не удалось отправить SMS. Попробуйте ещё раз через минуту.",
        ) from exc
    return {"detail": "Код отправлен", "ttl_minutes": OTP_TTL_MINUTES}


@router.post("/otp/verify", response_model=Token, summary="Подтвердить код и войти/зарегистрироваться")
def verify_otp(data: OTPVerify, db: Session = Depends(get_db)):
    otp = (
        db.query(OTPCode)
        .filter(OTPCode.phone == data.phone, OTPCode.is_used == False)  # noqa: E712
        .order_by(OTPCode.id.desc())
        .first()
    )
    if not otp or otp.code != data.code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неверный код")
    if otp.expires_at < datetime.utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Код истёк, запросите новый")

    otp.is_used = True

    user = db.query(User).filter(User.phone == data.phone).first()
    is_new_user = user is None
    if not user:
        user = User(phone=data.phone, full_name=data.full_name, role=UserRole.CLIENT)
        db.add(user)
        db.flush()

        if data.referral_code:
            referrer = db.query(User).filter(User.referral_code == data.referral_code.upper()).first()
            if referrer and referrer.id != user.id:
                user.referred_by_user_id = referrer.id
                # бонус за приглашение — по ананасу и приглашённому, и пригласившему
                for beneficiary in (user, referrer):
                    beneficiary.punch_count = (beneficiary.punch_count or 0) + 1
                    if beneficiary.punch_count > 12:
                        beneficiary.punch_count = 1
                    beneficiary.total_full_washes = (beneficiary.total_full_washes or 0) + 1
    db.commit()
    db.refresh(user)

    token = create_access_token(subject=str(user.id), role=user.role.value)
    return Token(access_token=token, role=user.role)


@router.post("/login", response_model=Token, summary="Вход по логину+паролю (клиент, сотрудник или админ)")
def login(data: StaffLogin, db: Session = Depends(get_db)):
    user = (
        db.query(User)
        .filter((User.username == data.login) | (User.phone == data.login))
        .first()
    )
    if not user or not user.password_hash or not verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")

    token = create_access_token(subject=str(user.id), role=user.role.value)
    return Token(access_token=token, role=user.role)


# Старый путь оставлен как алиас, чтобы не ломать то, что уже успело на него сослаться
@router.post("/staff/login", response_model=Token, include_in_schema=False)
def staff_login_alias(data: StaffLogin, db: Session = Depends(get_db)):
    return login(data, db)


@router.post("/set-password", response_model=UserOut, summary="Задать логин+пароль (доп. способ входа для клиента)")
def set_password(data: SetPassword, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == data.username, User.id != user.id).first()
    if existing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Такой логин уже занят")
    user.username = data.username
    user.password_hash = hash_password(data.password)
    db.commit()
    db.refresh(user)
    return user


@router.get("/me", response_model=UserOut, summary="Текущий пользователь")
def me(user: User = Depends(get_current_user)):
    return user
