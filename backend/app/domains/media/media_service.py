"""媒体上传服务（M6-media Task 2）：presign 直传契约 / 登记校验 / 列表 / 下载 URL。

白名单（brief 逐字）：扩展名 {".mp4", ".mov", ".webm"}、content_type
{"video/mp4", "video/quicktime", "video/webm"}、size ≤ 200MB。
object_key 由服务端签发 `media/{uuid4hex}{ext}`；登记时正则白名单校验防任意 key
注入（路径穿越/他人 key），head_bytes 读 16 字节做 magic number 校验
（mp4/mov: bytes[4:8] == b'ftyp'；webm: b'\\x1aE\\xdf\\xa3'），不符 → 422 并 remove。
mime 落库按 object_key 扩展名映射（POST /media 契约无 content_type 字段，见 brief）。

HTTP 契约模型（PresignIn/Out 等）集中在本模块：service 层直接返回类型化模型，
路由层只做 HTTP 编排与异常 → 状态码映射，避免 schemas 文件与 service 循环 import。
"""

import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn, cast

from fastapi import HTTPException
from minio.error import S3Error
from pydantic import BaseModel
from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.media.media_store import MediaStore, get_media_store
from app.models.media import MediaItem
from app.models.user import User

# ---- 白名单（brief 逐字） ----
ALLOWED_EXT = {".mp4", ".mov", ".webm"}
ALLOWED_MIME = {"video/mp4", "video/quicktime", "video/webm"}
MAX_SIZE = 200 * 1024 * 1024  # 200MB

MIME_BY_EXT = {".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm"}

# 预签直传窗口 / 下载 URL 有效期（秒）
PRESIGN_EXPIRES_S = 600
DOWNLOAD_EXPIRES_S = 3600

# 服务端签发的 key 格式（防任意 key 注入：路径穿越、他人 bucket 路径、大写扩展名）。
# 校验用 fullmatch 而非 $ 锚点：$ 允许结尾换行，"media/<32hex>.mp4\n" 会绕过格式门
# （本应 422 却放行到对象查询变 404）；fullmatch 要求整串匹配，杜绝该绕过。
KEY_RE = re.compile(r"media/[0-9a-f]{32}\.(mp4|mov|webm)")
MAGIC_LEN = 16  # head 读取长度：同时覆盖 mp4 ftyp（bytes 4-8）与 webm EBML 头（前 4 字节）
WEBM_MAGIC = b"\x1aE\xdf\xa3"


# ---- HTTP 契约模型 ----
class PresignIn(BaseModel):
    filename: str
    content_type: str
    size: int


class MediaRegisterIn(BaseModel):
    """登记请求体。不复用 auth 的 RegisterIn 同名类：FastAPI 对重名 schema 生成
    限定名（app__domains__...），会把 /auth/register 的 openapi ref 一并改成限定名，
    破坏外部按 `RegisterIn` 名引用的消费者。"""

    object_key: str
    filename: str
    size: int


class PresignOut(BaseModel):
    upload_url: str
    object_key: str
    expires_in: int


class MediaRegisteredOut(BaseModel):
    id: int
    status: str
    model_config = {"from_attributes": True}  # 从 MediaItem ORM 对象 model_validate


class MediaOut(BaseModel):
    id: int
    kind: str
    status: str
    size_bytes: int
    created_at: datetime
    model_config = {"from_attributes": True}


class MediaUrlOut(BaseModel):
    url: str
    expires_in: int


class MediaReviewIn(BaseModel):
    """admin 审核请求体：action ∈ {approve, reject}（白名单外 → 400）。"""

    action: str


class MediaReviewOut(BaseModel):
    id: int
    status: str


# 审核动作 → 目标状态（白名单映射，review_media 复用）
REVIEW_ACTIONS = {"approve": "approved", "reject": "rejected"}


# ---- 领域异常（路由层映射 HTTP 状态码，同 trip_service 的 ValueError 模式） ----
class MediaKeyInvalid(ValueError):
    """object_key 不符合签发格式或已被登记 → 422。"""


class MagicMismatch(ValueError):
    """对象内容与扩展名不符（对象已 remove）→ 422。"""


class MediaSizeMismatch(ValueError):
    """对象实际大小与登记声明不符（或超上限）（对象已 remove）→ 422。"""


class MediaObjectMissing(Exception):
    """对象存储中无此 key（客户端谎报已上传）→ 404。"""


class MediaNotFound(Exception):
    """媒体不存在或非本人 → 404。"""


class MediaNotApproved(Exception):
    """媒体未通过审核（pending/rejected）→ 403。"""


class InvalidReviewAction(ValueError):
    """审核动作不在 {approve, reject} 白名单 → 400。"""


class MediaAlreadyReviewed(Exception):
    """非 pending 状态再次审核（重复审核）→ 400。"""


def _check_ext(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ValueError("不支持的文件扩展名")
    return ext


def _magic_ok(head: bytes, ext: str) -> bool:
    if ext == ".webm":
        return head[:4] == WEBM_MAGIC
    return head[4:8] == b"ftyp"  # mp4/mov：ISO BMFF ftyp box（head 不足 8 字节时切片非全等 → False）


def _raise_store_error(e: KeyError | S3Error) -> NoReturn:
    """store 数据操作异常 → 统一语义（head_bytes / stat 共用）。

    KeyError（Fake 路径）/ S3Error(NoSuchKey) → MediaObjectMissing(404)；其余
    S3Error（AccessDenied/NoSuchBucket/5xx…）是基础设施故障，不得伪装成
    "对象不存在"——对象可能实际存在，伪装 404 会诱导用户重传并掩盖存储故障，
    → HTTPException(503) 交由上层告警。
    """
    if isinstance(e, KeyError) or (isinstance(e, S3Error) and e.code == "NoSuchKey"):
        raise MediaObjectMissing("对象不存在或已失效") from None
    raise HTTPException(status_code=503, detail="存储服务暂不可用") from None


async def presign_upload(
    session: AsyncSession, user: User, filename: str, content_type: str, size: int
) -> PresignOut:
    """直传预签：白名单校验 → 生成 key → presign_put。MVP 不写库（session/user
    留给后续配额/留痕，签名按 brief）；presign 无对象数据操作，store 走
    get_media_store() 单例（I-6 改 async 工厂，bucket 就绪由工厂 await 保证）。
    校验失败 → ValueError（路由映射 422）。
    """
    ext = _check_ext(filename)
    if content_type not in ALLOWED_MIME:
        raise ValueError("不支持的文件类型")
    if size <= 0:
        raise ValueError("文件大小必须为正")
    if size > MAX_SIZE:
        raise ValueError("文件超过 200MB 限制")
    object_key = f"media/{uuid.uuid4().hex}{ext}"
    store = await get_media_store()
    url = store.presign_put(object_key, content_type, PRESIGN_EXPIRES_S)
    return PresignOut(upload_url=url, object_key=object_key, expires_in=PRESIGN_EXPIRES_S)


async def register_media(
    session: AsyncSession,
    user: User,
    store: MediaStore,
    object_key: str,
    filename: str,
    size: int,
) -> MediaItem:
    """登记直传完成的对象：key 格式白名单 → 重复登记检查 → head 16 字节 magic
    校验 → stat 核真实大小（I-2）→ MediaItem(pending)。filename 为 brief 契约字段
    但模型无对应列，不落库。
    head/stat 失败语义：KeyError（Fake 路径）/ S3Error(NoSuchKey) →
    MediaObjectMissing(404)；其余 S3Error（AccessDenied/NoSuchBucket/5xx…）→
    HTTPException(503) 存储基础设施故障（映射收敛在 _raise_store_error）。
    大小核验（I-2）：stat 实测 != 声明 或 > MAX_SIZE → 422 并 remove，落库
    size_bytes 用实测值（客户端声明不再作为落库依据）。
    """
    if not KEY_RE.fullmatch(object_key):
        raise MediaKeyInvalid("object_key 格式非法")
    dup = (
        await session.execute(select(MediaItem).where(MediaItem.object_key == object_key))
    ).scalar_one_or_none()
    if dup is not None:  # 含"别人的合法格式 key"：object_key 全局唯一，先登记者得
        raise MediaKeyInvalid("object_key 已被登记")
    ext = f".{object_key.rsplit('.', 1)[1]}"  # 正则已保证 ∈ ALLOWED_EXT
    try:
        head = await store.head_bytes(object_key, MAGIC_LEN)
    except (KeyError, S3Error) as e:
        _raise_store_error(e)
    if not _magic_ok(head, ext):
        await store.remove(object_key)  # 不符 → 删除对象（防伪装/垃圾文件留存），对齐 S3 幂等语义
        raise MagicMismatch("文件内容与扩展名不符")
    try:
        actual = await store.stat(object_key)
    except (KeyError, S3Error) as e:  # head→stat 间隙对象被删 / 存储故障：同 head 语义
        _raise_store_error(e)
    if actual != size or actual > MAX_SIZE:
        await store.remove(object_key)  # 大小不符 → 删除对象，防谎报垃圾留存
        raise MediaSizeMismatch("文件大小与声明不符")
    item = MediaItem(
        user_id=user.id, object_key=object_key, size_bytes=actual, mime=MIME_BY_EXT[ext]
    )
    session.add(item)
    await session.commit()  # 项目约定 expire_on_commit=False（conftest/app.core.db），commit 后属性可用
    return item


async def my_media(session: AsyncSession, user_id: int) -> list[MediaItem]:
    """本人媒体列表（id desc）。"""
    result = await session.execute(
        select(MediaItem).where(MediaItem.user_id == user_id).order_by(MediaItem.id.desc())
    )
    return list(result.scalars().all())


async def download_url(
    session: AsyncSession, user: User, media_id: int, store: MediaStore
) -> MediaUrlOut:
    """下载 URL：本人 + approved 才发放 presign_get；pending/rejected → 403；他人/不存在 → 404。"""
    item = await session.get(MediaItem, media_id)
    if item is None or item.user_id != user.id:
        raise MediaNotFound("媒体不存在")
    if item.status != "approved":
        raise MediaNotApproved("未通过审核")
    url = await store.presign_get(item.object_key, DOWNLOAD_EXPIRES_S)
    return MediaUrlOut(url=url, expires_in=DOWNLOAD_EXPIRES_S)


async def review_media(session: AsyncSession, media_id: int, action: str) -> MediaItem:
    """admin 审核（M6-media Task 3 / M6.5 I-5 乐观并发）：pending → approved/rejected，
    状态机单向一次。

    rejected 不删除对象：留证优先（审核依据/申诉复查/审计），仅改 status 使
    download_url 持续 403，对象可随后续策略（定期清理）再处置。
    非法 action → InvalidReviewAction（400）；媒体不存在 → MediaNotFound（404）；
    非 pending 重复审核 → MediaAlreadyReviewed（400）。

    I-5：单条条件 UPDATE（WHERE id AND status='pending'）+ rowcount 判定，消除
    读后写竞态（两并发审核都读到 pending、后写覆盖先写）；rowcount==0 → 回查
    行存在性区分 404 / 已审核过，detail 文案与原实现一致。
    """
    target = REVIEW_ACTIONS.get(action)
    if target is None:
        raise InvalidReviewAction("非法审核动作")
    # rowcount 在运行时 CursorResult 上，不在类型化 Result 门面上（同 jwt_service 先例）
    res = cast(
        "CursorResult[Any]",
        await session.execute(
            update(MediaItem)
            .where(MediaItem.id == media_id, MediaItem.status == "pending")
            .values(status=target)
        ),
    )
    if res.rowcount == 0:
        item = await session.get(MediaItem, media_id)
        if item is None:
            raise MediaNotFound("媒体不存在")
        raise MediaAlreadyReviewed("已审核过")
    await session.commit()  # 项目约定 expire_on_commit=False，commit 后属性可用
    # UPDATE 不经 ORM identity map，回读落库行（scalar_one：rowcount==1 保证行存在）
    return (
        await session.execute(select(MediaItem).where(MediaItem.id == media_id))
    ).scalar_one()
