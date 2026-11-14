import jwt
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
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="令牌无效") from None
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="令牌类型错误")
    user = (await session.execute(
        select(User).where(User.id == int(payload["sub"]))
    )).scalar_one_or_none()
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=401, detail="账号不存在或已注销")
    if user.disabled:
        raise HTTPException(status_code=403, detail="账号已禁用")
    return user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    """admin 域专用依赖：仅放行 is_admin 用户（/admin 端点在 M5 Task 4 接入）。"""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
