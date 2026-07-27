"""
Диагностика входа. Запуск из папки carwash (там же, где requirements.txt):

    python -m app.scripts.diagnose

Покажет:
- какой файл БД реально используется (сравни путь с тем, что видит uvicorn при старте)
- сколько в базе пользователей и какие у них роли/логины
- проверит, подходит ли admin/admin
"""
import os
from app.database import SessionLocal, Base, engine
from app.models import User, UserRole, OTPCode
from app.security import verify_password
from app.config import settings

print("=" * 60)
print("DATABASE_URL из настроек:", settings.database_url)
if settings.database_url.startswith("sqlite"):
    path = settings.database_url.replace("sqlite:///", "")
    abspath = os.path.abspath(path)
    print("Абсолютный путь к файлу БД:", abspath)
    print("Файл существует:", os.path.exists(abspath))
print("=" * 60)

Base.metadata.create_all(bind=engine)
db = SessionLocal()

users = db.query(User).all()
print(f"\nВсего пользователей в базе: {len(users)}")
for u in users:
    print(f"  id={u.id} phone={u.phone} username={u.username} role={u.role.value} "
          f"есть_пароль={'да' if u.password_hash else 'нет'}")

admin = db.query(User).filter(User.username == "admin").first()
print("\nПроверка admin/admin:")
if not admin:
    print("  ❌ Пользователя с username='admin' в этой базе НЕТ.")
    print("     Значит seed выполнялся для ДРУГОГО файла БД, чем тот, что видит сервер.")
    print("     Реши так: убедись, что 'python -m app.seed' и 'uvicorn ...' запускаются")
    print("     из одной и той же папки (там, где requirements.txt).")
else:
    ok = admin.password_hash and verify_password("admin", admin.password_hash)
    print(f"  Пользователь найден (id={admin.id}). Пароль 'admin' подходит: {'✅ да' if ok else '❌ нет'}")

print(f"\nВсего кодов подтверждения (OTP) когда-либо создано: {db.query(OTPCode).count()}")
last_otp = db.query(OTPCode).order_by(OTPCode.id.desc()).first()
if last_otp:
    print(f"Последний код: телефон={last_otp.phone} код={last_otp.code} "
          f"использован={last_otp.is_used} истёк={last_otp.expires_at}")

db.close()
print("\nГотово.")
