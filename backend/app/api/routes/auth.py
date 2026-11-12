from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import verify_password
from app.main import limiter
from app.schemas.auth import LoginIn, RefreshIn, RegisterIn, UserOut
from app.services import auth_service, user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
async def register(data: RegisterIn, session: AsyncSession = Depends(get_session)) -> UserOut:
    try:
        user = await user_service.create_user(session, data)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="邮箱或手机号已注册") from None
    return UserOut.model_validate(user)


@router.post("/login")
@limiter.limit("10/minute")
async def login(
    request: Request, data: LoginIn, session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    user = await user_service.get_by_identity(session, data.email, data.phone)
    if (
        not user
        or user.deleted_at
        or not user.password_hash
        or not verify_password(data.password, user.password_hash)
    ):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    return await auth_service.issue_pair(session, user)


@router.post("/refresh")
async def refresh(data: RefreshIn, session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    try:
        return await auth_service.rotate(session, data.refresh_token)
    except LookupError:
        raise HTTPException(status_code=401, detail="刷新令牌无效") from None
    except PermissionError:
        raise HTTPException(status_code=401, detail="刷新令牌已被使用，已吊销全部会话") from None


@router.post("/logout")
async def logout(data: RefreshIn, session: AsyncSession = Depends(get_session)) -> dict[str, bool]:
    await auth_service.revoke(session, data.refresh_token)
    return {"ok": True}
