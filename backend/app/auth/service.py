from datetime import datetime, timedelta, timezone

import jwt
import secrets
from cachetools import TTLCache
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.platform.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.platform.database import get_db
from app.auth.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# auto_error=False：缺 Bearer 时返回 None，由本模块统一抛 401（避免 FastAPI 默认 403）
security_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None


def _user_from_jwt(token: str, db: Session) -> User | None:
    payload = decode_access_token(token)
    if payload is None:
        return None
    user_id_str = payload.get("sub")
    if user_id_str is None:
        return None
    try:
        user_id = int(user_id_str)
    except (TypeError, ValueError):
        return None
    return db.query(User).filter(User.id == user_id).first()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未认证",
        )
    user = _user_from_jwt(credentials.credentials, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证令牌",
        )
    return user


class RequireRole:
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        if current_user.role.value not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足",
            )
        return current_user


TICKETS: TTLCache = TTLCache(maxsize=10000, ttl=30)


def create_ticket(user: User) -> dict:
    ticket = secrets.token_urlsafe(32)
    TICKETS[ticket] = user.id
    return {"ticket": ticket, "expires_in": 30}


def _resolve_user_via_ticket(ticket: str, db: Session) -> User | None:
    """一次性 ticket（query ?ticket=）；用后作废。"""
    user_id = TICKETS.pop(ticket, None)
    if user_id is None:
        return None
    return db.query(User).filter(User.id == user_id).first()


def get_current_user_by_ticket(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """SSE / 文件下载等无法带 Authorization Header 的路由专用。

    凭证顺序：
      1. Header ``Authorization: Bearer`` JWT（仅 Header，不放 query）
      2. query ``ticket``（POST /ticket 签发的一次性凭证）

    已废弃：query ``token`` 传 JWT（Referer/日志泄露风险）。
    """
    auth_header = request.headers.get("authorization", "")
    parts = auth_header.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        bearer = parts[1].strip()
        if bearer:
            user = _user_from_jwt(bearer, db)
            if user:
                return user
            raise HTTPException(status_code=401, detail="无效凭证")

    ticket = request.query_params.get("ticket")
    if ticket:
        user = _resolve_user_via_ticket(ticket, db)
        if user:
            return user
        raise HTTPException(status_code=401, detail="无效凭证")

    raise HTTPException(status_code=401, detail="未认证")
