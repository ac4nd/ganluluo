import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.core.security import verify_password
from app.main import limiter
from app.models.user import User
from app.schemas.auth import LoginIn, LogoutOut, RefreshIn, RegisterIn, TokenPair, UserOut
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


@router.post("/login", response_model=TokenPair)
@limiter.limit("10/minute")
async def login(
    request: Request, data: LoginIn, session: AsyncSession = Depends(get_session)
) -> TokenPair:
    user = await user_service.get_by_identity(session, data.email, data.phone)
    if (
        not user
        or user.deleted_at
        or not user.password_hash
        or not verify_password(data.password, user.password_hash)
    ):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    return await auth_service.issue_pair(session, user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(data: RefreshIn, session: AsyncSession = Depends(get_session)) -> TokenPair:
    try:
        return await auth_service.rotate(session, data.refresh_token)
    except PermissionError as exc:
        if str(exc) == "refresh token reuse detected":
            raise HTTPException(status_code=401, detail="刷新令牌已被使用，已吊销全部会话") from None
        raise HTTPException(status_code=401, detail="刷新令牌无效") from None
    except (ValueError, jwt.InvalidTokenError, LookupError):
        raise HTTPException(status_code=401, detail="刷新令牌无效") from None


@router.post("/logout", response_model=LogoutOut)
async def logout(data: RefreshIn, session: AsyncSession = Depends(get_session)) -> LogoutOut:
    try:
        await auth_service.revoke(session, data.refresh_token)
    except (ValueError, jwt.InvalidTokenError, LookupError, PermissionError):
        raise HTTPException(status_code=401, detail="刷新令牌无效") from None
    return LogoutOut(ok=True)


@router.get("/me", response_model=UserOut)
async def me(current: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current)
