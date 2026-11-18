import hashlib

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_session
from app.core.rate_limit import limiter
from app.core.security import verify_password
from app.domains.auth import jwt_service as auth_service
from app.domains.auth import service as user_service
from app.domains.auth.schemas import (
    LoginIn,
    LogoutOut,
    RefreshIn,
    RegisterIn,
    TokenPair,
    UserOut,
    WechatLoginIn,
)
from app.models.user import User

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
    # 禁用账号：密码正确也不签发（login 在 router 而非 service.py，故拦在此处）
    if user.disabled:
        raise HTTPException(status_code=403, detail="账号已禁用")
    return await auth_service.issue_pair(session, user)


@router.post("/wechat-login", response_model=TokenPair)
@limiter.limit("10/minute")
async def wechat_login(
    request: Request, data: WechatLoginIn, session: AsyncSession = Depends(get_session)
) -> TokenPair:
    """微信一键登录（M8）：wx.login() code 换 openid → 查/建用户 → 签发 TokenPair。

    配置齐全走真实 jscode2session；未配置时 dev 用确定性 mock（同 code 同用户），
    prod 拒绝 503（mock 通道不得在生产可达）。
    """
    s = get_settings()
    if s.wechat_appid and s.wechat_secret:
        # 真实路径：外联在 service 层（外联前过 assert_safe_external_url）
        try:
            body = await user_service.jscode2session(s.wechat_appid, s.wechat_secret, data.code)
        except user_service.WechatUpstreamError:
            raise HTTPException(status_code=502, detail="微信服务不可达") from None
        # 微信成功响应无 errcode 字段；errcode 非 0 或缺 openid 一律 401
        if body.get("errcode") or not body.get("openid"):
            raise HTTPException(status_code=401, detail="微信登录失败")
        openid = str(body["openid"])
    elif s.env == "prod":
        raise HTTPException(status_code=503, detail="微信登录未配置")
    else:
        openid = "wxmock_" + hashlib.sha256(data.code.encode()).hexdigest()[:24]
    user = await user_service.get_or_create_by_oauth(session, "wechat", openid, data.nickname)
    # 禁用账号拒绝登录（同 /auth/login 口径：密码对也不发 token）
    if user.disabled:
        raise HTTPException(status_code=403, detail="账号已禁用")
    return await auth_service.issue_pair(session, user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(data: RefreshIn, session: AsyncSession = Depends(get_session)) -> TokenPair:
    try:
        return await auth_service.rotate(session, data.refresh_token)
    except PermissionError as exc:
        if str(exc) == "refresh token reuse detected":
            raise HTTPException(status_code=401, detail="刷新令牌已被使用，已吊销全部会话") from None
        if str(exc) == "account disabled":
            raise HTTPException(status_code=403, detail="账号已禁用") from None
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
