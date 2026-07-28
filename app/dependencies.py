from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/staff/login", auto_error=False)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось подтвердить учётные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_error

    payload = decode_access_token(token)
    if not payload:
        raise credentials_error

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise credentials_error
    return user


def require_roles(*roles: UserRole):
    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав для этого действия",
            )
        return user
    return _dep


require_admin = require_roles(UserRole.ADMIN)
require_staff = require_roles(UserRole.ADMIN, UserRole.MASTER)
require_manager_or_admin = require_roles(UserRole.ADMIN, UserRole.MANAGER)
# просмотр графика/сотрудников — шире, включая руководителя (он должен видеть, чтобы редактировать)
require_staff_read = require_roles(UserRole.ADMIN, UserRole.MASTER, UserRole.MANAGER)
# изменение графика и списка сотрудников — админ и руководитель (не рядовой мойщик)
require_schedule_write = require_roles(UserRole.ADMIN, UserRole.MANAGER)
