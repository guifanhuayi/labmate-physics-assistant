from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.api.auth import read_current_session
from app.auth.errors import AuthError
from app.auth.service import CurrentSession
from app.db.session import get_db


Db = Annotated[Session, Depends(get_db)]
Current = Annotated[CurrentSession, Depends(read_current_session)]


def require_roles(current: CurrentSession, *roles: str) -> None:
    if current.user.role not in roles:
        raise AuthError("forbidden", "你没有权限执行此操作。", 403)
