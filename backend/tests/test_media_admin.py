"""M6-media Task 3：/admin 媒体审核 API（分页列表 + approve/reject 状态机）。

media_client 夹具本地定义（同 test_media_api：每测试独立 FakeMediaStore；跨测试模块
import 夹具会被 ruff 判 F401/F811，项目惯例只跨模块 import 常量/普通函数）；
_registered_media 全流程造数；admin 身份同 test_admin_api 惯例——register_and_login
后 db 直改 is_admin=True（get_current_admin 每请求查库，与签发时点无关）。
审核衔接验证：admin approve 后用户侧 /media/{id}/url 必须从 403 变 200。
测试用户一律经 register_and_login（无字面量凭据）。
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.db import get_session
from app.domains.media.media_router import get_store
from app.domains.media.media_store import FakeMediaStore
from app.main import create_app
from app.models.media import MediaItem
from app.models.user import User

from .test_auth_login import register_and_login
from .test_media_api import _auth, _registered_media


@pytest_asyncio.fixture
async def media_client(db):
    """client + 每测试独立 FakeMediaStore（用法：c, store = media_client）；定义同 test_media_api。"""
    app = create_app()
    store = FakeMediaStore()

    async def override_session():
        yield db

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_store] = lambda: store
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, store


async def _admin(c, db, email="adm@b.com"):
    """注册登录后置 is_admin=True，返回 admin headers。"""
    tokens = await register_and_login(c, email=email)
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    user.is_admin = True
    await db.commit()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_admin_media_endpoints_require_admin_403(media_client):
    """get_current_admin 真实端点链路：普通用户访问媒体列表/审核端点 → 403。"""
    c, _ = media_client
    tokens = await register_and_login(c, email="plain@b.com")
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = await c.get("/admin/media", headers=h)
    assert r.status_code == 403 and r.json()["detail"] == "需要管理员权限"
    r = await c.post("/admin/media/1/review", json={"action": "approve"}, headers=h)
    assert r.status_code == 403 and r.json()["detail"] == "需要管理员权限"


async def test_media_list_pending_default_filter_and_pagination(media_client, db):
    """默认 pending 队列 + status 过滤（白名单外 422）+ 分页（id asc，Query 校验同 /admin/users）。"""
    c, store = media_client
    ah = await _admin(c, db, email="listadm@b.com")
    h, uid = await _auth(c, "uploader@b.com")
    for _ in range(3):
        await _registered_media(c, store, h)
    ids = sorted(
        i.id for i in (await db.execute(select(MediaItem).where(MediaItem.user_id == uid))).scalars()
    )
    assert len(ids) == 3
    # 翻两态：一条 approved、一条 rejected，剩一条 pending
    (await db.get(MediaItem, ids[0])).status = "approved"
    (await db.get(MediaItem, ids[1])).status = "rejected"
    await db.commit()
    # 默认 status=pending：只剩 ids[2]
    r = await c.get("/admin/media", headers=ah)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1 and body["page"] == 1 and body["size"] == 20
    assert [i["id"] for i in body["items"]] == [ids[2]]
    got = body["items"][0]
    assert set(got) == {"id", "user_id", "kind", "status", "size_bytes", "created_at"}  # 契约字段
    assert got["user_id"] == uid and got["kind"] == "video" and got["status"] == "pending"
    assert got["size_bytes"] == 12345 and "T" in got["created_at"]
    # status 过滤：approved / rejected
    r = await c.get("/admin/media?status=approved", headers=ah)
    assert r.status_code == 200 and [i["id"] for i in r.json()["items"]] == [ids[0]]
    r = await c.get("/admin/media?status=rejected", headers=ah)
    assert r.status_code == 200 and [i["id"] for i in r.json()["items"]] == [ids[1]]
    # status 白名单外 → 422
    assert (await c.get("/admin/media?status=bogus", headers=ah)).status_code == 422
    # 分页：再补两条 pending（共 3 条）→ size=2 两页，id asc 跨页稳定
    await _registered_media(c, store, h)
    await _registered_media(c, store, h)
    pending_ids = sorted(
        i.id
        for i in (
            await db.execute(
                select(MediaItem).where(MediaItem.user_id == uid, MediaItem.status == "pending")
            )
        ).scalars()
    )
    assert len(pending_ids) == 3 and pending_ids[0] == ids[2]
    p1 = (await c.get("/admin/media?status=pending&size=2&page=1", headers=ah)).json()
    p2 = (await c.get("/admin/media?status=pending&size=2&page=2", headers=ah)).json()
    assert p1["total"] == 3 and p2["total"] == 3
    assert [i["id"] for i in p1["items"]] == pending_ids[:2]
    assert [i["id"] for i in p2["items"]] == pending_ids[2:]
    all_ids = [i["id"] for i in p1["items"]] + [i["id"] for i in p2["items"]]
    assert all_ids == sorted(all_ids)
    # Query 校验：page>=1、size 1-100
    assert (await c.get("/admin/media?page=0", headers=ah)).status_code == 422
    assert (await c.get("/admin/media?size=0", headers=ah)).status_code == 422
    assert (await c.get("/admin/media?size=101", headers=ah)).status_code == 422


async def test_review_approve_then_user_url_403_to_200(media_client, db):
    """审核衔接：pending → 用户 url 403；admin approve → 200 {id, status}；用户 url 403→200。"""
    c, store = media_client
    ah = await _admin(c, db, email="approvadm@b.com")
    h, _ = await _auth(c, "approvee@b.com")
    key, r = await _registered_media(c, store, h)
    mid = r.json()["id"]
    # pending：用户侧取 url 403
    assert (await c.get(f"/media/{mid}/url", headers=h)).status_code == 403
    # admin approve → 200 {id, status}
    res = await c.post(f"/admin/media/{mid}/review", json={"action": "approve"}, headers=ah)
    assert res.status_code == 200 and res.json() == {"id": mid, "status": "approved"}
    # 衔接验证：用户侧 url 从 403 变 200，url 含 object_key
    ok = await c.get(f"/media/{mid}/url", headers=h)
    assert ok.status_code == 200 and key in ok.json()["url"]
    # 列表随动：默认 pending 不再含 mid，?status=approved 含 mid
    pending_ids = [i["id"] for i in (await c.get("/admin/media", headers=ah)).json()["items"]]
    approved_ids = [i["id"] for i in (await c.get("/admin/media?status=approved", headers=ah)).json()["items"]]
    assert mid not in pending_ids and mid in approved_ids


async def test_review_reject_keeps_object_and_url_403(media_client, db):
    """reject：对象不删（留证）仅改 status，用户侧 url 持续 403。"""
    c, store = media_client
    ah = await _admin(c, db, email="rejadm@b.com")
    h, _ = await _auth(c, "rejectee@b.com")
    key, r = await _registered_media(c, store, h)
    mid = r.json()["id"]
    res = await c.post(f"/admin/media/{mid}/review", json={"action": "reject"}, headers=ah)
    assert res.status_code == 200 and res.json() == {"id": mid, "status": "rejected"}
    assert key in store._objects  # rejected 不删对象：留证（审核依据/申诉复查/审计）
    row = await db.get(MediaItem, mid)
    assert row is not None and row.status == "rejected"  # 行也在（只改状态不删行/对象）
    u = await c.get(f"/media/{mid}/url", headers=h)
    assert u.status_code == 403 and u.json()["detail"] == "未通过审核"


async def test_review_repeat_400(media_client, db):
    """重复审核 400：approve 后再 approve / 再 reject 都 400 "已审核过"。"""
    c, store = media_client
    ah = await _admin(c, db, email="repeatadm@b.com")
    h, _ = await _auth(c, "repeater@b.com")
    _, r = await _registered_media(c, store, h)
    mid = r.json()["id"]
    first = await c.post(f"/admin/media/{mid}/review", json={"action": "approve"}, headers=ah)
    assert first.status_code == 200
    for action in ("approve", "reject"):
        res = await c.post(f"/admin/media/{mid}/review", json={"action": action}, headers=ah)
        assert res.status_code == 400 and res.json()["detail"] == "已审核过"


async def test_review_invalid_action_400(media_client, db):
    """action 白名单外 → 400 "非法审核动作"，媒体状态不被改动。"""
    c, store = media_client
    ah = await _admin(c, db, email="actadm@b.com")
    h, _ = await _auth(c, "actor@b.com")
    _, r = await _registered_media(c, store, h)
    mid = r.json()["id"]
    res = await c.post(f"/admin/media/{mid}/review", json={"action": "delete"}, headers=ah)
    assert res.status_code == 400 and res.json()["detail"] == "非法审核动作"
    # 状态未被破坏：仍在默认 pending 列表
    body = (await c.get("/admin/media", headers=ah)).json()
    assert body["total"] == 1 and body["items"][0]["status"] == "pending"


async def test_review_unknown_media_404(media_client, db):
    c, _ = media_client
    ah = await _admin(c, db, email="nfadm@b.com")
    res = await c.post("/admin/media/999999/review", json={"action": "approve"}, headers=ah)
    assert res.status_code == 404 and res.json()["detail"] == "媒体不存在"
