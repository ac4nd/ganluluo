from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import decode_token
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    session: AsyncSession = Depends(get_session),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = decode_token(credentials.credentials)
    except Exception:
        raise HTTPException(status_code=401, detail="令牌无效") from None
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="令牌类型错误")
    user = (await session.execute(
        select(User).where(User.id == int(payload["sub"]))
    )).scalar_one_or_none()
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=401, detail="账号不存在或已注销")
    return user
