import secrets

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http import assert_safe_external_url
from app.core.security import hash_password
from app.domains.admin.quota_service import seed_tiers
from app.domains.auth.schemas import RegisterIn
from app.models.profile import UserProfile
from app.models.user import User

# 微信 jscode2session 端点（M8 一键登录）：公网 https host，外联前过 SSRF 防护
WECHAT_JSCODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"


class WechatUpstreamError(Exception):
    """微信上游不可达（超时/连接失败）：router 映射 502。"""


async def jscode2session(appid: str, secret: str, code: str) -> dict:
    """真实路径换 openid：外联 jscode2session，返回微信 JSON（含 openid 或 errcode）。

    测试 monkeypatch 点（router 不直接依赖 httpx；patch 本函数即可离线覆盖真实
    路径，且 assert_safe_external_url 的 DNS 解析不进测试路径）。
    """
    assert_safe_external_url(WECHAT_JSCODE2SESSION_URL)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                WECHAT_JSCODE2SESSION_URL,
                params={"appid": appid, "secret": secret, "js_code": code,
                        "grant_type": "authorization_code"},
            )
    except httpx.HTTPError as exc:
        raise WechatUpstreamError("微信服务不可达") from exc
    return resp.json()


async def create_user(session: AsyncSession, data: RegisterIn) -> User:
    user = User(
        email=data.email,
        phone=data.phone,
        nickname=data.nickname,
        password_hash=hash_password(data.password),
    )
    session.add(user)
    await session.commit()
    # 注册即建默认画像（sports=[] exp_level=1 fitness=2）
    session.add(UserProfile(user_id=user.id))
    await session.commit()
    # 注册时确保配额档位存在（M5-admin Task 2）：seed_tiers 幂等，quota_tiers 空库首注册
    # 补 trial/vip 两行。users.quota_tier 由列默认 'trial' 承载，无需按用户建行。
    await seed_tiers(session)
    await session.refresh(user)
    return user


async def get_by_identity(session: AsyncSession, email: str | None, phone: str | None) -> User | None:
    stmt = select(User).where(User.deleted_at.is_(None))
    if email:
        stmt = stmt.where(User.email == email)
    else:
        stmt = stmt.where(User.phone == phone)
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_or_create_by_oauth(
    session: AsyncSession, provider: str, subject: str, nickname: str | None
) -> User:
    """按 oauth 身份查/建用户（M8 一键登录）：软删除用户视为不存在，另起新号。

    建号不设 email/phone（oauth 用户无邮箱密码凭据），nickname 缺省"徒步者"+4 位
    随机数字；建后 seed_tiers 确保配额档位行存在（幂等，同 create_user 先例）。
    """
    stmt = select(User).where(
        User.oauth_provider == provider,
        User.oauth_subject == subject,
        User.deleted_at.is_(None),
    )
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user:
        return user
    if not nickname:
        nickname = "徒步者" + f"{secrets.randbelow(10000):04d}"
    user = User(nickname=nickname, oauth_provider=provider, oauth_subject=subject)
    session.add(user)
    await session.commit()
    await seed_tiers(session)
    await session.refresh(user)
    return user
