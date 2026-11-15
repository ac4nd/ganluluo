"""媒体用户 API（M6-media Task 2）：presign 直传 / 登记 / 本人列表 / 下载 URL。

路由层只做 HTTP 编排与异常 → 状态码映射；白名单/魔法数校验下沉 media_service。
store 经 get_store 依赖注入（测试用 app.dependency_overrides[get_store] 换每测试
独立的 FakeMediaStore，避免对象串数据；与 agent_provider 覆盖模式一致）。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.domains.media import media_service
from app.domains.media.media_service import (
    MagicMismatch,
    MediaKeyInvalid,
    MediaNotApproved,
    MediaNotFound,
    MediaObjectMissing,
    MediaOut,
    MediaRegisteredOut,
    MediaRegisterIn,
    MediaUrlOut,
    PresignIn,
    PresignOut,
)
from app.domains.media.media_store import MediaStore, get_media_store
from app.models.user import User

router = APIRouter()


def get_store() -> MediaStore:
    """store 依赖：生产走 get_media_store() 单例；测试 dependency_overrides 注入 Fake。"""
    return get_media_store()


@router.post("/presign", response_model=PresignOut)
async def presign(
    data: PresignIn,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PresignOut:
    try:
        return media_service.presign_upload(session, current, data.filename, data.content_type, data.size)
    except ValueError as e:  # 白名单拒绝：扩展名 / content_type / size
        raise HTTPException(status_code=422, detail=str(e)) from None


@router.post("", response_model=MediaRegisteredOut, status_code=201)
async def register_media(
    data: MediaRegisterIn,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    store: MediaStore = Depends(get_store),
) -> MediaRegisteredOut:
    try:
        item = await media_service.register_media(session, current, store, data.object_key, data.filename, data.size)
    except (MediaKeyInvalid, MagicMismatch) as e:  # key 白名单 / 魔法数不符（对象已 remove）
        raise HTTPException(status_code=422, detail=str(e)) from None
    except MediaObjectMissing as e:  # 谎报已上传：store 中无此对象
        raise HTTPException(status_code=404, detail=str(e)) from None
    return MediaRegisteredOut.model_validate(item)


@router.get("/my", response_model=list[MediaOut])
async def my_media(
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[MediaOut]:
    items = await media_service.my_media(session, current.id)
    return [MediaOut.model_validate(i) for i in items]


@router.get("/{media_id}/url", response_model=MediaUrlOut)
async def media_url(
    media_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    store: MediaStore = Depends(get_store),
) -> MediaUrlOut:
    try:
        return await media_service.download_url(session, current, media_id, store)
    except MediaNotFound as e:  # 不存在或非本人
        raise HTTPException(status_code=404, detail=str(e)) from None
    except MediaNotApproved as e:  # pending/rejected：未过审核不放 URL
        raise HTTPException(status_code=403, detail=str(e)) from None
