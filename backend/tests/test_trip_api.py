"""M4 Task 2：/trips CRUD API + 计划卡装备提醒。

测试注册用户一律经 register_and_login（非字面量凭据）；
装备差集造数据直接 db.add(UserGear)（同 test_trip_service.py 的 service 层造数先例）。
"""

from app.models.gear import UserGear
from app.seeds.seed_routes import seed_routes

from .test_auth_login import register_and_login

# seed_routes 首条"雨崩"线的必备装备与摘要（契约断言用）
REQUIRED = ["rain-gear", "midlayer", "boots", "first-aid"]
TRIP_BODY = {"route_id": 1, "date": "2026-11-20", "meet_at": "08:30", "meet_place": "飞来寺观景台"}


async def _auth(client, email: str):
    """注册登录并返回 (headers, user_id)。"""
    tokens = await register_and_login(client, email=email)
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    uid = (await client.get("/auth/me", headers=h)).json()["id"]
    return h, uid


async def test_create_201_full_card(client, db):
    await seed_routes(db)
    h, uid = await _auth(client, "trip@b.com")
    r = await client.post("/trips", json=TRIP_BODY, headers=h)
    assert r.status_code == 201
    body = r.json()
    # TripPlanOut 契约字段
    assert body["id"] > 0
    assert body["user_id"] == uid
    assert body["route_id"] == 1
    assert body["date"] == "2026-11-20"
    assert body["meet_at"] == "08:30:00"
    assert body["meet_place"] == "飞来寺观景台"
    assert body["status"] == "planned"
    # 路线摘要
    assert body["route_name"].startswith("雨崩")
    assert body["region"] == "云南迪庆州德钦县·梅里雪山"
    assert body["sport"] == "hiking"
    assert body["difficulty"] == 3
    assert body["distance_km"] == 26.7
    assert body["climb_m"] == 941
    assert body["duration_h"] == 18.0
    # 用户无任何装备 → 必带装备全部进入提醒，且保持路线顺序
    assert body["gear_missing"] == REQUIRED


async def test_get_single_gear_complete_missing_empty(client, db):
    await seed_routes(db)
    h, uid = await _auth(client, "full@b.com")
    tid = (await client.post("/trips", json=TRIP_BODY, headers=h)).json()["id"]
    for key in REQUIRED:
        db.add(UserGear(user_id=uid, item_key=key))
    await db.commit()
    r = await client.get(f"/trips/{tid}", headers=h)
    assert r.status_code == 200
    assert r.json()["gear_missing"] == []


async def test_list_cards(client, db):
    await seed_routes(db)
    h, _ = await _auth(client, "list@b.com")
    await client.post("/trips", json=TRIP_BODY, headers=h)
    await client.post(
        "/trips", json={"route_id": 2, "date": "2026-11-21", "meet_at": "07:00"}, headers=h
    )
    r = await client.get("/trips", headers=h)
    assert r.status_code == 200 and len(r.json()) == 2
    by_name = {c["route_name"]: c for c in r.json()}
    yubeng = by_name["雨崩徒步（神瀑+冰湖精华线）"]
    assert yubeng["gear_missing"] == REQUIRED
    hutiao = by_name["虎跳峡高路徒步（一日精华段）"]
    assert hutiao["meet_place"] is None  # 未传 meet_place → null
    assert hutiao["gear_missing"] == ["boots", "sunscreen", "rain-gear"]


async def test_patch_status_done(client, db):
    await seed_routes(db)
    h, _ = await _auth(client, "done@b.com")
    tid = (await client.post("/trips", json=TRIP_BODY, headers=h)).json()["id"]
    r = await client.patch(f"/trips/{tid}/status", json={"status": "done"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "done"
    r = await client.get(f"/trips/{tid}", headers=h)
    assert r.json()["status"] == "done"


async def test_list_status_filter(client, db):
    """F-2：status 过滤——05「最近足迹」取 done、07「日期轴」取 planned。"""
    await seed_routes(db)
    h, _ = await _auth(client, "filter@b.com")
    planned = (await client.post("/trips", json=TRIP_BODY, headers=h)).json()["id"]
    done_body = {"route_id": 2, "date": "2026-11-21", "meet_at": "07:00"}
    done = (await client.post("/trips", json=done_body, headers=h)).json()["id"]
    await client.patch(f"/trips/{done}/status", json={"status": "done"}, headers=h)

    r = await client.get("/trips", headers=h)
    assert {c["id"] for c in r.json()} == {planned, done}
    r = await client.get("/trips", params={"status": "planned"}, headers=h)
    assert [c["id"] for c in r.json()] == [planned]
    r = await client.get("/trips", params={"status": "done"}, headers=h)
    assert [c["id"] for c in r.json()] == [done]
    r = await client.get("/trips", params={"status": "nope"}, headers=h)
    assert r.status_code == 422


async def test_patch_invalid_status_400(client, db):
    await seed_routes(db)
    h, _ = await _auth(client, "badstatus@b.com")
    tid = (await client.post("/trips", json=TRIP_BODY, headers=h)).json()["id"]
    r = await client.patch(f"/trips/{tid}/status", json={"status": "finished"}, headers=h)
    assert r.status_code == 400 and r.json()["detail"] == "非法行程状态"


async def test_patch_and_get_others_plan_404(client, db):
    await seed_routes(db)
    h1, _ = await _auth(client, "owner@b.com")
    tid = (await client.post("/trips", json=TRIP_BODY, headers=h1)).json()["id"]
    h2, _ = await _auth(client, "intruder@b.com")
    r = await client.patch(f"/trips/{tid}/status", json={"status": "done"}, headers=h2)
    assert r.status_code == 404
    r = await client.get(f"/trips/{tid}", headers=h2)
    assert r.status_code == 404


async def test_delete_204_then_get_404(client, db):
    await seed_routes(db)
    h, _ = await _auth(client, "del@b.com")
    tid = (await client.post("/trips", json=TRIP_BODY, headers=h)).json()["id"]
    r = await client.delete(f"/trips/{tid}", headers=h)
    assert r.status_code == 204
    r = await client.get(f"/trips/{tid}", headers=h)
    assert r.status_code == 404
    r = await client.patch(f"/trips/{tid}/status", json={"status": "done"}, headers=h)
    assert r.status_code == 404
    r = await client.delete(f"/trips/{tid}", headers=h)
    assert r.status_code == 404


async def test_post_invalid_route_404(client, db):
    h, _ = await _auth(client, "badroute@b.com")
    r = await client.post("/trips", json={**TRIP_BODY, "route_id": 999}, headers=h)
    assert r.status_code == 404
    assert "路线不存在或未发布" in r.json()["detail"]


async def test_requires_auth(client):
    r = await client.get("/trips")
    assert r.status_code == 401
    r = await client.post("/trips", json=TRIP_BODY)
    assert r.status_code == 401
    r = await client.patch("/trips/1/status", json={"status": "done"})
    assert r.status_code == 401
    r = await client.delete("/trips/1")
    assert r.status_code == 401
