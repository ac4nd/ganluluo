"""M4 Task 3：POST /assistant/plan 一键从对话槽位生成行程计划。

测试用户一律 register_and_login（非字面量凭据）；澄清会话直造（clarify 形状同
orchestrator 落库的 ClarifyState dump）；卡片契约断言同 test_trip_api.py 基线。
"""

from datetime import date, timedelta

from app.assistant import session_store
from app.seeds.seed_routes import seed_routes

from .test_auth_login import register_and_login

# seed_routes 首条"雨崩"线的必备装备与摘要（契约断言用）
REQUIRED = ["rain-gear", "midlayer", "boots", "first-aid"]


async def _auth(client, email: str):
    """注册登录并返回 (headers, user_id)。"""
    tokens = await register_and_login(client, email=email)
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    uid = (await client.get("/auth/me", headers=h)).json()["id"]
    return h, uid


async def _plan_session(db, uid: int, slots: dict) -> str:
    """造一个带澄清槽位的本人会话，返回 session_id。"""
    sess = await session_store.create_session(db, uid, title="plan")
    await session_store.set_clarify(
        db, sess.id, {"intent": "plan", "slots": slots, "asked": [], "round_no": 2}
    )
    return sess.id


async def test_explicit_route_and_date_200(client, db):
    await seed_routes(db)
    h, uid = await _auth(client, "plan@b.com")
    r = await client.post(
        "/assistant/plan",
        json={"route_id": 1, "date": "2026-11-20", "meet_at": "08:30", "meet_place": "飞来寺观景台"},
        headers=h,
    )
    assert r.status_code == 200
    body = r.json()
    # TripPlanOut 契约字段
    assert body["id"] > 0
    assert body["user_id"] == uid
    assert body["route_id"] == 1
    assert body["date"] == "2026-11-20"
    assert body["meet_at"] == "08:30:00"
    assert body["meet_place"] == "飞来寺观景台"
    assert body["status"] == "planned"
    # 路线摘要 + 装备提醒（与 /trips 卡片同构）
    assert body["route_name"].startswith("雨崩")
    assert body["region"] == "云南迪庆州德钦县·梅里雪山"
    assert body["sport"] == "hiking"
    assert body["difficulty"] == 3
    assert body["distance_km"] == 26.7
    assert body["climb_m"] == 941
    assert body["duration_h"] == 18.0
    assert body["gear_missing"] == REQUIRED


async def test_session_slots_top1_and_default_meet_at(client, db):
    await seed_routes(db)
    h, uid = await _auth(client, "slot@b.com")
    # region 槽位用 REGION_KEYWORDS 中能命中种子路线 region 列的词（"梅里"仅
    # 命中雨崩线；"雨崩"只出现在路线名里，list_routes 的 region ilike 不匹配）
    sid = await _plan_session(db, uid, {"sport": "hiking", "region": "梅里"})
    r = await client.post(
        "/assistant/plan", json={"session_id": sid, "date": "2026-11-20"}, headers=h
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == uid
    assert body["route_id"] == 1  # 槽位过滤后唯一候选（雨崩线）即 top1
    assert body["route_name"].startswith("雨崩")
    assert body["meet_at"] == "08:00:00"  # meet_at 缺省 → 08:00
    assert body["meet_place"] is None
    assert body["gear_missing"] == REQUIRED


async def test_date_from_slot_parsed(client, db):
    await seed_routes(db)
    h, uid = await _auth(client, "date@b.com")
    sid = await _plan_session(db, uid, {"sport": "hiking", "region": "梅里", "date": "周六"})
    r = await client.post("/assistant/plan", json={"session_id": sid}, headers=h)
    assert r.status_code == 200
    plan_date = date.fromisoformat(r.json()["date"])
    today = date.today()
    # "周六" → 今天（含）起下一个周六
    assert plan_date.weekday() == 5
    assert today <= plan_date <= today + timedelta(days=6)


async def test_no_session_no_route_422(client, db):
    await seed_routes(db)
    h, _ = await _auth(client, "nosess@b.com")
    r = await client.post("/assistant/plan", json={"date": "2026-11-20"}, headers=h)
    assert r.status_code == 422
    assert r.json()["detail"] == "无法确定路线"


async def test_no_date_422(client, db):
    await seed_routes(db)
    h, _ = await _auth(client, "nodate@b.com")
    r = await client.post("/assistant/plan", json={"route_id": 2}, headers=h)
    assert r.status_code == 422
    assert r.json()["detail"] == "无法确定日期"


async def test_other_user_session_422(client, db):
    await seed_routes(db)
    _h1, uid1 = await _auth(client, "owner@b.com")
    sid = await _plan_session(db, uid1, {"sport": "hiking", "region": "雨崩"})
    h2, _ = await _auth(client, "intruder@b.com")
    r = await client.post(
        "/assistant/plan", json={"session_id": sid, "date": "2026-11-20"}, headers=h2
    )
    # own_session 返回 None → 按"无会话"处理
    assert r.status_code == 422
    assert r.json()["detail"] == "无法确定路线"


async def test_no_candidates_404(client, db):
    await seed_routes(db)
    h, uid = await _auth(client, "empty@b.com")
    sid = await _plan_session(db, uid, {"sport": "underwater-hockey", "region": "雨崩"})
    r = await client.post(
        "/assistant/plan", json={"session_id": sid, "date": "2026-11-20"}, headers=h
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "无匹配路线"


async def test_requires_auth(client):
    r = await client.post("/assistant/plan", json={"route_id": 1, "date": "2026-11-20"})
    assert r.status_code == 401
