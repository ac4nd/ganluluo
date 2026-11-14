"""M5-admin Task 4：/admin 管理 API（用户管理 + 路线审核）。

夹具同 test_trip_api.py（create_app + override get_session）；admin 身份用
register_and_login 后 db 直改 is_admin=True（最稳：password_hash 正确；已有
access token 依旧有效——get_current_admin 每请求查库读 is_admin，与签发时点无关）。

交接①：PATCH disable 必须显式吊销该用户全部 refresh tokens —— 被禁后 refresh 走
401（token 已烧），而不是 disabled 用户的 403 分支；re-enable 后旧 token 也不得复活。
交接②：get_current_admin 真实端点链路 —— 普通用户访问任一 /admin 端点 → 403。
配额档位：usage 用例显式 seed_tiers 造档（trial/vip 限额经 API 回读）；缺档兜底
路径已在 service 层 test_quota_service.test_status_falls_back_without_tier_row 覆盖。
"""

from sqlalchemy import select

from app.core.security import decode_token
from app.domains.admin.quota_service import record_usage, seed_tiers
from app.models.route import Route
from app.models.user import User
from app.seeds.seed_routes import seed_routes

from .test_auth_login import register_and_login


async def _admin(client, db, email="adm@b.com"):
    """注册登录后置 is_admin=True，返回 (headers, admin_id)。"""
    tokens = await register_and_login(client, email=email)
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    user.is_admin = True
    await db.commit()
    return {"Authorization": f"Bearer {tokens['access_token']}"}, user.id


async def _user_id(client, email: str) -> int:
    tokens = await register_and_login(client, email=email)
    return int(decode_token(tokens["access_token"])["sub"])


async def _draft(db, name: str) -> Route:
    route = Route(name=name, region="云南迪庆州", sport="hiking", distance_km=10.0, status="draft")
    db.add(route)
    await db.commit()
    return route


async def test_admin_endpoints_require_admin_403(client):
    """交接②：get_current_admin 真实端点链路——普通用户访问任一 /admin 端点 → 403。"""
    tokens = await register_and_login(client, email="plain@b.com")
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    responses = [
        await client.get("/admin/users", headers=h),
        await client.patch("/admin/users/1", json={"disabled": False}, headers=h),
        await client.get("/admin/users/1/usage", headers=h),
        await client.get("/admin/routes/drafts", headers=h),
        await client.post("/admin/routes/1/publish", headers=h),
    ]
    for r in responses:
        assert r.status_code == 403
        assert r.json()["detail"] == "需要管理员权限"


async def test_users_list_search_and_pagination(client, db):
    ah, _ = await _admin(client, db, email="root@b.com")
    for e in ("alice1@b.com", "alice2@b.com", "alice3@b.com", "bob@b.com"):
        await register_and_login(client, email=e)
    r = await client.get("/admin/users", headers=ah)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 5 and body["page"] == 1 and body["size"] == 20
    ids = [i["id"] for i in body["items"]]
    assert ids == sorted(ids) and len(ids) == 5  # id asc 稳定排序
    item = next(i for i in body["items"] if i["email"] == "alice1@b.com")
    # 列表 item 契约字段（created_at ISO）
    assert set(item) == {"id", "email", "nickname", "quota_tier", "is_admin", "disabled", "created_at"}
    assert item["quota_tier"] == "trial" and item["disabled"] is False and item["is_admin"] is False
    assert "T" in item["created_at"]
    me = next(i for i in body["items"] if i["email"] == "root@b.com")
    assert me["is_admin"] is True  # admin 自己也在列表
    # email ilike 搜索
    r = await client.get("/admin/users?query=alice", headers=ah)
    assert r.json()["total"] == 3
    # nickname ilike 搜索（register_and_login 的 nickname 一律 "晨"）
    r = await client.get("/admin/users?query=晨", headers=ah)
    assert r.json()["total"] == 5
    # 分页：size=2 page=2 → 第 3、4 条
    r = await client.get("/admin/users?size=2&page=2", headers=ah)
    b = r.json()
    assert b["total"] == 5 and b["page"] == 2 and [i["id"] for i in b["items"]] == ids[2:4]


async def test_patch_quota_tier_vip_and_usage_values(client, db):
    ah, _ = await _admin(client, db, email="tieradm@b.com")
    vid = await _user_id(client, "tier@b.com")
    await seed_tiers(db)  # 显式造档：trial 5/20000、vip 50/500000
    for _ in range(2):
        await record_usage(db, vid, "s1", "m", 100, 50)
    r = await client.get(f"/admin/users/{vid}/usage", headers=ah)
    assert r.status_code == 200
    assert r.json() == {
        "chats_used": 2, "tokens_used": 300, "tier": "trial",
        "daily_chats_limit": 5, "daily_tokens_limit": 20000, "allowed": True,
    }
    # patch → vip 200 回读
    r = await client.patch(f"/admin/users/{vid}", json={"quota_tier": "vip"}, headers=ah)
    assert r.status_code == 200
    assert r.json()["quota_tier"] == "vip"
    # usage 反映 vip 档限额
    r = await client.get(f"/admin/users/{vid}/usage", headers=ah)
    assert r.json()["tier"] == "vip"
    assert r.json()["daily_chats_limit"] == 50 and r.json()["daily_tokens_limit"] == 500000
    # 未知用户 usage → 404
    r = await client.get("/admin/users/9999/usage", headers=ah)
    assert r.status_code == 404


async def test_patch_invalid_tier_400(client, db):
    ah, _ = await _admin(client, db, email="badtier@b.com")
    vid = await _user_id(client, "badtieru@b.com")
    r = await client.patch(f"/admin/users/{vid}", json={"quota_tier": "gold"}, headers=ah)
    assert r.status_code == 400 and r.json()["detail"] == "非法配额档位"
    # 原值未被破坏
    r = await client.get(f"/admin/users/{vid}/usage", headers=ah)
    assert r.json()["tier"] == "trial"


async def test_patch_self_disable_400(client, db):
    ah, admin_id = await _admin(client, db, email="selfdis@b.com")
    r = await client.patch(f"/admin/users/{admin_id}", json={"disabled": True}, headers=ah)
    assert r.status_code == 400 and r.json()["detail"] == "不能禁用自己"


async def test_patch_unknown_user_404(client, db):
    ah, _ = await _admin(client, db, email="nousr@b.com")
    r = await client.patch("/admin/users/9999", json={"quota_tier": "vip"}, headers=ah)
    assert r.status_code == 404 and r.json()["detail"] == "用户不存在"


async def test_patch_empty_body_unchanged_200(client, db):
    """宽松处理（brief 允许）：两字段都缺省 → 原样返回 200。"""
    ah, _ = await _admin(client, db, email="emptyadm@b.com")
    vid = await _user_id(client, "emptyu@b.com")
    r = await client.patch(f"/admin/users/{vid}", json={}, headers=ah)
    assert r.status_code == 200
    body = r.json()
    assert body["quota_tier"] == "trial" and body["disabled"] is False


async def test_disable_revokes_refresh_tokens_no_resurrect(client, db):
    """交接①：disable=True 显式吊销该用户全部 refresh tokens。

    被禁后 refresh → 401（token 已烧，吊销先于 disabled 判定命中），而非 disabled
    用户的 403 分支；re-enable 后旧 token 也不得复活续期（Task 1 审查发现的复活 bug）。
    """
    ah, _ = await _admin(client, db, email="revadm@b.com")
    tokens = await register_and_login(client, email="victim@b.com")
    vid = int(decode_token(tokens["access_token"])["sub"])
    r = await client.patch(f"/admin/users/{vid}", json={"disabled": True}, headers=ah)
    assert r.status_code == 200 and r.json()["disabled"] is True
    r = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401  # 非 403：证明 token 已被吊销烧掉
    # re-enable：旧 refresh token 不得复活
    r = await client.patch(f"/admin/users/{vid}", json={"disabled": False}, headers=ah)
    assert r.status_code == 200 and r.json()["disabled"] is False
    r = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401


async def test_drafts_list_desc_order(client, db):
    await seed_routes(db)  # published 种子线不进草稿列表
    ah, _ = await _admin(client, db, email="draftadm@b.com")
    d1 = await _draft(db, "草稿甲")
    d2 = await _draft(db, "草稿乙")
    r = await client.get("/admin/routes/drafts", headers=ah)
    assert r.status_code == 200
    body = r.json()
    assert [x["id"] for x in body] == [d2.id, d1.id]  # id desc
    assert set(body[0]) == {"id", "name", "region", "sport", "created_at"}
    assert body[0]["name"] == "草稿乙"


async def test_publish_then_visible_and_unknown_404(client, db):
    await seed_routes(db)
    ah, _ = await _admin(client, db, email="pubadm@b.com")
    d = await _draft(db, "待发布线")
    assert "待发布线" not in {r["name"] for r in (await client.get("/routes")).json()}
    r = await client.post(f"/admin/routes/{d.id}/publish", headers=ah)
    assert r.status_code == 200
    assert r.json() == {"ok": True, "status": "published"}
    # 发布后 GET /routes（published 过滤）可见
    assert "待发布线" in {r["name"] for r in (await client.get("/routes")).json()}
    # 未知路线 404
    r = await client.post("/admin/routes/9999/publish", headers=ah)
    assert r.status_code == 404


async def test_publish_non_draft_400(client, db):
    await seed_routes(db)
    ah, _ = await _admin(client, db, email="nondraft@b.com")
    published = (
        await db.execute(select(Route).where(Route.status == "published"))
    ).scalars().first()
    r = await client.post(f"/admin/routes/{published.id}/publish", headers=ah)
    assert r.status_code == 400 and r.json()["detail"] == "路线非草稿状态"
    # 刚发布的草稿再发布 → 400
    d = await _draft(db, "发布一次")
    assert (await client.post(f"/admin/routes/{d.id}/publish", headers=ah)).status_code == 200
    r = await client.post(f"/admin/routes/{d.id}/publish", headers=ah)
    assert r.status_code == 400 and r.json()["detail"] == "路线非草稿状态"
