import secrets
import bcrypt
from datetime import datetime, timedelta
from typing import Optional

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.config import settings

_serializer = URLSafeTimedSerializer(settings.secret_key, salt="avtomoyka1-auth")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("utf-8"))


def generate_otp_code() -> str:
    return f"{secrets.randbelow(10_000):04d}"


def create_access_token(subject: str, role: str, expires_minutes: Optional[int] = None) -> str:
    # itsdangerous сам подписывает и умеет проверять "возраст" токена (max_age при decode),
    # поэтому срок жизни не кладём внутрь payload, а передаём при проверке.
    return _serializer.dumps({"sub": subject, "role": role})


def decode_access_token(token: str, expires_minutes: Optional[int] = None) -> Optional[dict]:
    max_age = (expires_minutes or settings.access_token_expire_minutes) * 60
    try:
        return _serializer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
