"""M6-media Task 2：/media 用户 API（presign 直传 / 登记 / 列表 / 下载 URL）。

测试注册用户一律经 register_and_login（非字面量凭据）；store 依赖注入每测试
独立 FakeMediaStore（避免对象串数据），get_session override 同 conftest 模式；
approved/rejected 态直接改 DB 造（审核端点在 Task 3）。
"""

import re
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from minio.error import S3Error
from sqlalchemy import select

from app.core.db import get_session
from app.domains.media.media_router import get_store
from app.domains.media.media_service import DOWNLOAD_EXPIRES_S, MAX_SIZE, PRESIGN_EXPIRES_S
from app.domains.media.media_store import FakeMediaStore
from app.main import create_app
from app.models.media import MediaItem

from .test_auth_login import register_and_login

MP4_HEAD = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00"  # bytes[4:8] == b'ftyp'
WEBM_HEAD = b"\x1aE\xdf\xa3\x1fB\x86\x81"  # EBML 头
PRESIGN_BODY = {"filename": "clip.mp4", "content_type": "video/mp4", "size": 12345}
MIME_BY_EXT = {"mp4": "video/mp4", "mov": "video/quicktime", "webm": "video/webm"}
HEAD_BY_EXT = {"mp4": MP4_HEAD, "mov": MP4_HEAD, "webm": WEBM_HEAD}


@pytest_asyncio.fixture
async def media_client(db):
    """client + 每测试独立 FakeMediaStore（用法：c, store = media_client）。"""
    app = create_app()
    store = FakeMediaStore()

    async def override_session():
        yield db

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_store] = lambda: store
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, store


async def _auth(c, email: str):
    """注册登录并返回 (headers, user_id)。"""
    tokens = await register_and_login(c, email=email)
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    uid = (await c.get("/auth/me", headers=h)).json()["id"]
    return h, uid


async def _registered_media(c, store, h, ext="mp4"):
    """走完 presign → 预置魔法数对象（内容按声明 size 补齐，过 I-2 stat 核验）→
    登记 全流程，返回 (object_key, response)。"""
    body = {"filename": f"clip.{ext}", "content_type": MIME_BY_EXT[ext], "size": 12345}
    key = (await c.post("/media/presign", json=body, headers=h)).json()["object_key"]
    store.put(key, HEAD_BY_EXT[ext].ljust(body["size"], b"\x00"))
    r = await c.post(
        "/media", json={"object_key": key, "filename": body["filename"], "size": body["size"]}, headers=h
    )
    return key, r


async def test_presign_ok_and_key_format(media_client):
    c, _ = media_client
    h, _ = await _auth(c, "presign@b.com")
    r = await c.post("/media/presign", json=PRESIGN_BODY, headers=h)
    assert r.status_code == 200
    body = r.json()
    # object_key 必须是服务端签发格式：media/{uuid4hex}.mp4
    assert re.fullmatch(r"media/[0-9a-f]{32}\.mp4", body["object_key"])
    assert body["object_key"] in body["upload_url"]
    assert body["expires_in"] == PRESIGN_EXPIRES_S


async def test_presign_whitelist_rejects(media_client):
    c, _ = media_client
    h, _ = await _auth(c, "reject@b.com")
    cases = [
        {"filename": "notes.txt", "content_type": "text/plain", "size": 10},  # 扩展名+mime 双拒
        {"filename": "clip.avi", "content_type": "video/x-msvideo", "size": 10},  # 非白名单容器
        {"filename": "clip.mp4", "content_type": "video/mp4", "size": MAX_SIZE + 1},  # 超 200MB
        {"filename": "clip.mp4", "content_type": "video/mp4", "size": 0},  # 非正 size
        {"filename": "clip.mp4", "content_type": "video/mp4", "size": -1},
    ]
    for body in cases:
        r = await c.post("/media/presign", json=body, headers=h)
        assert r.status_code == 422, body


async def test_register_201_pending(media_client, db):
    c, store = media_client
    h, _ = await _auth(c, "reg@b.com")
    key, r = await _registered_media(c, store, h)
    assert r.status_code == 201
    body = r.json()
    assert body["id"] > 0 and body["status"] == "pending"
    key2, r2 = await _registered_media(c, store, h, ext="webm")  # webm magic 分支
    assert r2.status_code == 201 and r2.json()["status"] == "pending"
    # 落库：mime 从 object_key 扩展名映射
    rows = {i.object_key: i for i in (await db.execute(select(MediaItem))).scalars()}
    assert rows[key].mime == "video/mp4" and rows[key].kind == "video"
    assert rows[key].size_bytes == 12345 and rows[key2].mime == "video/webm"


async def test_register_magic_mismatch_422_removes_object(media_client):
    c, store = media_client
    h, _ = await _auth(c, "magic@b.com")
    body = {"filename": "evil.mp4", "content_type": "video/mp4", "size": 32}
    key = (await c.post("/media/presign", json=body, headers=h)).json()["object_key"]
    store.put(key, b"MZ" + b"x" * 30)  # 伪装成 mp4 的非视频内容
    r = await c.post(
        "/media", json={"object_key": key, "filename": body["filename"], "size": 32}, headers=h
    )
    assert r.status_code == 422
    assert key not in store._objects  # 魔法数不符 → 对象已被 remove


async def test_register_size_mismatch_422_removes_object(media_client):
    """I-2 stat 核真实大小：put 短内容 + 登记声明大 size → 422 且对象被 remove。"""
    c, store = media_client
    h, _ = await _auth(c, "sizelie@b.com")
    body = {"filename": "clip.mp4", "content_type": "video/mp4", "size": 12345}
    key = (await c.post("/media/presign", json=body, headers=h)).json()["object_key"]
    store.put(key, HEAD_BY_EXT["mp4"])  # 只 16 字节魔法头：实测 != 声明
    r = await c.post(
        "/media", json={"object_key": key, "filename": body["filename"], "size": body["size"]}, headers=h
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "文件大小与声明不符"
    assert key not in store._objects  # 大小不符 → 对象已被 remove


async def test_register_size_over_max_422(media_client, monkeypatch):
    """I-2：实测 > 200MB 上限（声明合规）→ 422 并 remove（monkeypatch stat 模拟超大对象）。"""
    c, store = media_client
    h, _ = await _auth(c, "sizebig@b.com")
    body = {"filename": "clip.mp4", "content_type": "video/mp4", "size": 12345}
    key = (await c.post("/media/presign", json=body, headers=h)).json()["object_key"]
    store.put(key, HEAD_BY_EXT["mp4"].ljust(12345, b"\x00"))

    async def stat_huge(key: str) -> int:
        return MAX_SIZE + 1

    monkeypatch.setattr(store, "stat", stat_huge)
    r = await c.post(
        "/media", json={"object_key": key, "filename": body["filename"], "size": 12345}, headers=h
    )
    assert r.status_code == 422 and r.json()["detail"] == "文件大小与声明不符"
    assert key not in store._objects


async def test_register_persists_actual_size(media_client):
    """I-2 落库实测值：声明 == 实测（12345）→ /media/my 回读 size_bytes == 12345。"""
    c, store = media_client
    h, _ = await _auth(c, "sizeok@b.com")
    _, r = await _registered_media(c, store, h)
    assert r.status_code == 201
    items = (await c.get("/media/my", headers=h)).json()
    assert items[0]["size_bytes"] == 12345  # 与 store 实测一致，非客户端可伪造值


async def test_register_unknown_object_404(media_client):
    c, _ = media_client
    h, _ = await _auth(c, "ghost@b.com")
    key = f"media/{uuid.uuid4().hex}.mp4"  # 格式合法但从未上传（谎报）
    r = await c.post("/media", json={"object_key": key, "filename": "clip.mp4", "size": 10}, headers=h)
    assert r.status_code == 404
    assert r.json()["detail"] == "对象不存在或已失效"


def _s3_stub_error(code: str) -> S3Error:
    """真实 S3Error 对象（minio 7.x 8 参签名；response 仅属性存储无运行时校验，None 即可）。"""
    return S3Error(None, code, "stub message", "/", "req", "host")


def _head_boom(code: str):
    """head_bytes 替身：抛指定 code 的 S3Error，模拟真实 MinIO 存储侧故障。
    I-6 async 化后 head_bytes 为 async 协议方法，替身同签名 async。"""

    async def boom(key: str, n: int) -> bytes:
        raise _s3_stub_error(code)

    return boom


async def test_register_s3_nosuchkey_still_404(media_client, monkeypatch):
    """S3Error(NoSuchKey) = 对象确实不存在 → 语义收窄后仍维持 404 契约。"""
    c, store = media_client
    h, _ = await _auth(c, "nosuchkey@b.com")
    key = f"media/{uuid.uuid4().hex}.mp4"
    monkeypatch.setattr(store, "head_bytes", _head_boom("NoSuchKey"))
    r = await c.post("/media", json={"object_key": key, "filename": "clip.mp4", "size": 10}, headers=h)
    assert r.status_code == 404
    assert r.json()["detail"] == "对象不存在或已失效"


async def test_register_s3_infra_error_503(media_client, monkeypatch):
    """其余 S3Error（AccessDenied/NoSuchBucket/5xx 类）是基础设施故障 → 503，不得伪装成 404。"""
    c, store = media_client
    h, _ = await _auth(c, "s3down@b.com")
    key = f"media/{uuid.uuid4().hex}.mp4"
    monkeypatch.setattr(store, "head_bytes", _head_boom("AccessDenied"))
    r = await c.post("/media", json={"object_key": key, "filename": "clip.mp4", "size": 10}, headers=h)
    assert r.status_code == 503
    assert r.json()["detail"] == "存储服务暂不可用"


async def test_register_invalid_and_foreign_key_422(media_client):
    c, store = media_client
    h1, _ = await _auth(c, "owner@b.com")
    # key 注入面：路径穿越 / 非签发前缀 / 非 hex / 非白名单扩展名
    for bad in ("media/../../x.mp4", "../x.mp4", "media/zzzz.mp4", f"media/{uuid.uuid4().hex}.avi"):
        r = await c.post("/media", json={"object_key": bad, "filename": "clip.mp4", "size": 10}, headers=h1)
        assert r.status_code == 422, bad
    # 别人已登记的合法格式 key → 422（object_key 全局唯一，先登记者得）
    key, _ = await _registered_media(c, store, h1)
    h2, _ = await _auth(c, "intruder@b.com")
    r = await c.post("/media", json={"object_key": key, "filename": "clip.mp4", "size": 10}, headers=h2)
    assert r.status_code == 422


async def test_register_key_trailing_newline_422(media_client):
    """格式门用 fullmatch：合法 key 加结尾换行不得放行（$ 锚点会被 \n 绕过，本应 422 却 404）。"""
    c, _ = media_client
    h, _ = await _auth(c, "newline@b.com")
    key = f"media/{uuid.uuid4().hex}.mp4\n"
    r = await c.post("/media", json={"object_key": key, "filename": "clip.mp4", "size": 10}, headers=h)
    assert r.status_code == 422
    assert r.json()["detail"] == "object_key 格式非法"


async def test_my_list_desc_and_contract(media_client, db):
    c, store = media_client
    h, uid = await _auth(c, "list@b.com")
    assert (await c.get("/media/my", headers=h)).json() == []  # 空列表
    _, r = await _registered_media(c, store, h)
    db.add(MediaItem(user_id=uid, object_key=f"media/{uuid.uuid4().hex}.mp4", size_bytes=1, mime="video/mp4"))
    await db.commit()
    res = await c.get("/media/my", headers=h)
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 2
    ids = [i["id"] for i in items]
    assert ids == sorted(ids, reverse=True)  # id desc
    assert set(items[0]) == {"id", "kind", "status", "size_bytes", "created_at"}  # 契约字段
    assert items[-1]["id"] == r.json()["id"] and items[-1]["kind"] == "video" and items[-1]["status"] == "pending"


async def test_url_three_states(media_client, db):
    c, store = media_client
    h1, _ = await _auth(c, "urlown@b.com")
    key, r = await _registered_media(c, store, h1)
    mid = r.json()["id"]
    # pending → 403
    p = await c.get(f"/media/{mid}/url", headers=h1)
    assert p.status_code == 403 and p.json()["detail"] == "未通过审核"
    # rejected → 403（DB 直改造状态）
    item = await db.get(MediaItem, mid)
    item.status = "rejected"
    await db.commit()
    assert (await c.get(f"/media/{mid}/url", headers=h1)).status_code == 403
    # approved → 200，url 含 object_key
    item.status = "approved"
    await db.commit()
    ok = await c.get(f"/media/{mid}/url", headers=h1)
    assert ok.status_code == 200
    body = ok.json()
    assert key in body["url"] and body["expires_in"] == DOWNLOAD_EXPIRES_S
    # 他人 → 404；不存在 → 404
    h2, _ = await _auth(c, "urlpeek@b.com")
    assert (await c.get(f"/media/{mid}/url", headers=h2)).status_code == 404
    assert (await c.get("/media/999999/url", headers=h1)).status_code == 404


async def test_requires_auth(media_client):
    c, _ = media_client
    r = await c.post("/media/presign", json=PRESIGN_BODY)
    assert r.status_code == 401
    r = await c.post("/media", json={"object_key": f"media/{uuid.uuid4().hex}.mp4", "filename": "c.mp4", "size": 1})
    assert r.status_code == 401
    r = await c.get("/media/my")
    assert r.status_code == 401
    r = await c.get("/media/1/url")
    assert r.status_code == 401
