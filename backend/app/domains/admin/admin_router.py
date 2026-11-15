"""管理 API（M5-admin Task 4 + M6-media Task 3）：/admin 用户管理、路线审核与媒体审核。

7 端点全部 Depends(get_current_admin)（Task 1 依赖）：普通用户 403 "需要管理员权限"，
禁用账号在其上游 get_current_user 即 403 "账号已禁用"。

媒体审核两端点复用 media_service（状态机 review_media / 审核动作白名单）：
rejected 不删对象（留证），仅改 status 使用户侧 download_url 持续 403。

交接①：PATCH 置 disabled=True 时必须显式吊销该用户全部 refresh tokens
（jwt_service._revoke_all）：Task 1 审查实测 refresh 的 disabled 分支 claim 更新未
commit，不吊销则已签发的 refresh token 在 re-enable 后复活续期。
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.db import get_session
from app.domains.admin.quota_service import get_status
from app.domains.auth.jwt_service import _revoke_all
from app.domains.media import media_service
from app.domains.media.media_service import (
    InvalidReviewAction,
    MediaAlreadyReviewed,
    MediaNotFound,
    MediaReviewIn,
    MediaReviewOut,
)
from app.models.media import MediaItem
from app.models.route import Route
from app.models.user import User

router = APIRouter()

VALID_TIERS = {"trial", "vip"}
VALID_MEDIA_STATUS = {"pending", "approved", "rejected"}


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str | None
    nickname: str
    quota_tier: str
    is_admin: bool
    disabled: bool
    created_at: datetime


class UserPageOut(BaseModel):
    items: list[AdminUserOut]
    total: int
    page: int
    size: int


class UserPatchIn(BaseModel):
    quota_tier: str | None = None
    disabled: bool | None = None


class UsageOut(BaseModel):
    chats_used: int
    tokens_used: int
    tier: str
    daily_chats_limit: int
    daily_tokens_limit: int
    allowed: bool


class DraftRouteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    region: str
    sport: str
    created_at: datetime


class PublishOut(BaseModel):
    ok: bool
    status: str


class AdminMediaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    kind: str
    status: str
    size_bytes: int
    created_at: datetime


class MediaPageOut(BaseModel):
    items: list[AdminMediaOut]
    total: int
    page: int
    size: int


async def _live_user(session: AsyncSession, user_id: int) -> User | None:
    """按 id 取未注销用户（deleted_at 口径同 get_current_user 的"账号不存在或已注销"）。"""
    return (
        await session.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
    ).scalar_one_or_none()


@router.get("/users", response_model=UserPageOut)
async def list_users(
    query: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> UserPageOut:
    stmt = select(User).where(User.deleted_at.is_(None))
    if query:
        like = f"%{query}%"
        stmt = stmt.where(User.email.ilike(like) | User.nickname.ilike(like))
    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    rows = (
        await session.execute(stmt.order_by(User.id).offset((page - 1) * size).limit(size))
    ).scalars().all()
    return UserPageOut(items=[AdminUserOut.model_validate(u) for u in rows], total=total, page=page, size=size)


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def patch_user(
    user_id: int,
    payload: UserPatchIn,
    admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminUserOut:
    user = await _live_user(session, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if payload.quota_tier is not None and payload.quota_tier not in VALID_TIERS:
        raise HTTPException(status_code=400, detail="非法配额档位")
    if payload.disabled and user.id == admin.id:
        raise HTTPException(status_code=400, detail="不能禁用自己")
    # 宽松处理（brief 允许）：两字段都缺省 → 原样返回 200
    if payload.quota_tier is not None:
        user.quota_tier = payload.quota_tier
    if payload.disabled is not None:
        user.disabled = payload.disabled
    if payload.disabled:
        # 交接①：烧掉该用户全部 refresh tokens，否则 re-enable 后旧 token 复活续期；
        # 吊销后 refresh 走 401 而非 disabled 403 分支。
        # I-2：disable 路径不再提前 commit——_revoke_all 内部 UPDATE + commit 收尾时
        # 用户字段变更随同一次提交，消除"字段已提交、吊销未提交"中间崩溃 + 之后
        # re-enable 让旧 refresh token 复活续期的窗口。
        await _revoke_all(session, user.id)
    else:
        await session.commit()
    return AdminUserOut.model_validate(user)


@router.get("/users/{user_id}/usage", response_model=UsageOut)
async def user_usage(
    user_id: int,
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> UsageOut:
    user = await _live_user(session, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    status = await get_status(session, user_id, user.quota_tier)
    return UsageOut(
        chats_used=status.daily_chats_used,
        tokens_used=status.daily_tokens_used,
        tier=user.quota_tier,
        daily_chats_limit=status.daily_chats_limit,
        daily_tokens_limit=status.daily_tokens_limit,
        allowed=status.allowed,
    )


@router.get("/routes/drafts", response_model=list[DraftRouteOut])
async def list_drafts(
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> list[DraftRouteOut]:
    rows = (
        await session.execute(
            select(Route).where(Route.status == "draft").order_by(Route.id.desc())
        )
    ).scalars().all()
    return [DraftRouteOut.model_validate(r) for r in rows]


@router.post("/routes/{route_id}/publish", response_model=PublishOut)
async def publish_route(
    route_id: int,
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> PublishOut:
    route = (
        await session.execute(select(Route).where(Route.id == route_id))
    ).scalar_one_or_none()
    if route is None:
        raise HTTPException(status_code=404, detail="路线不存在")
    if route.status != "draft":
        raise HTTPException(status_code=400, detail="路线非草稿状态")
    route.status = "published"
    await session.commit()
    return PublishOut(ok=True, status="published")


@router.get("/media", response_model=MediaPageOut)
async def list_media(
    status: str = Query("pending"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> MediaPageOut:
    """媒体审核分页列表：默认 pending 待审队列；status 白名单外 → 422；按 id asc（同 /admin/users）。"""
    if status not in VALID_MEDIA_STATUS:
        raise HTTPException(status_code=422, detail="非法媒体状态")
    stmt = select(MediaItem).where(MediaItem.status == status)
    total = (
        await session.execute(select(func.count()).select_from(stmt.subquery()))
    ).scalar_one()
    rows = (
        await session.execute(stmt.order_by(MediaItem.id).offset((page - 1) * size).limit(size))
    ).scalars().all()
    return MediaPageOut(items=[AdminMediaOut.model_validate(m) for m in rows], total=total, page=page, size=size)


@router.post("/media/{media_id}/review", response_model=MediaReviewOut)
async def review_media(
    media_id: int,
    payload: MediaReviewIn,
    _admin: User = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
) -> MediaReviewOut:
    """审核：pending → approved/rejected；rejected 不删对象（留证，见 media_service.review_media）。"""
    try:
        item = await media_service.review_media(session, media_id, payload.action)
    except InvalidReviewAction as e:  # action 白名单（approve/reject）外
        raise HTTPException(status_code=400, detail=str(e)) from None
    except MediaNotFound as e:  # 媒体不存在
        raise HTTPException(status_code=404, detail=str(e)) from None
    except MediaAlreadyReviewed as e:  # 非 pending 重复审核
        raise HTTPException(status_code=400, detail=str(e)) from None
    return MediaReviewOut(id=item.id, status=item.status)
