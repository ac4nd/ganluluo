from app.seeds.seed_routes import seed_routes

from .test_track_service import GPX


async def test_list_with_filters(client, db):
    await seed_routes(db)
    r = await client.get("/routes", params={"sport": "hiking", "difficulty_max": 3})
    assert r.status_code == 200
    names = {x["name"] for x in r.json()}
    assert "虎跳峡高路徒步（一日精华段）" in names
    assert "五台山顺朝（三天两夜大朝台）" not in names


async def test_region_filter_matches_route_name(client, db):
    # "雨崩"只出现在路线名（region 列是"云南迪庆州德钦县·梅里雪山"），
    # region 过滤按 region 列 OR name 列匹配后命中
    await seed_routes(db)
    r = await client.get("/routes", params={"region": "雨崩"})
    assert r.status_code == 200
    names = {x["name"] for x in r.json()}
    assert names == {"雨崩徒步（神瀑+冰湖精华线）"}


async def test_region_filter_still_matches_region_column(client, db):
    # 回归保护：region 列词（"迪庆"）仍命中雨崩线 + 虎跳峡线
    await seed_routes(db)
    r = await client.get("/routes", params={"region": "迪庆"})
    assert r.status_code == 200
    names = {x["name"] for x in r.json()}
    assert names == {"雨崩徒步（神瀑+冰湖精华线）", "虎跳峡高路徒步（一日精华段）"}


async def test_region_filter_no_match_returns_empty(client, db):
    await seed_routes(db)
    r = await client.get("/routes", params={"region": "不存在的地区"})
    assert r.status_code == 200
    assert r.json() == []


async def test_get_detail(client, db):
    await seed_routes(db)
    r = await client.get("/routes/1")
    assert r.status_code == 200
    body = r.json()
    assert body["name"].startswith("雨崩")
    assert isinstance(body["elevation"], list)
    assert body["track_points"] is None  # 种子路线无轨迹


async def test_detail_exposes_track_points_after_upload(client, db):
    """F-3：上传处理后详情暴露 track_points（08 高程折线/3D 飞行数据源）。"""
    await seed_routes(db)
    await client.post("/routes/1/track", content=GPX.encode(),
                      headers={"Content-Type": "text/plain"})
    r = await client.get("/routes/1")
    assert r.status_code == 200
    pts = r.json()["track_points"]
    assert pts and all(set(p) == {"lat", "lon", "ele"} for p in pts)


async def test_get_detail_404(client, db):
    r = await client.get("/routes/999")
    assert r.status_code == 404


async def test_track_upload_updates_route(client, db):
    await seed_routes(db)
    r = await client.post("/routes/1/track", content=GPX.encode(), headers={"Content-Type": "text/plain"})
    assert r.status_code == 200
    assert r.json()["distance_km"] > 0


async def test_track_upload_404(client, db):
    r = await client.post("/routes/999/track", content=b"<gpx/>", headers={"Content-Type": "text/plain"})
    assert r.status_code == 404


async def test_create_requires_auth(client, db):
    r = await client.post("/routes", json={"name": "n", "region": "r", "sport": "hiking",
                                           "difficulty": 2, "distance_km": 5.0, "climb_m": 100})
    assert r.status_code == 401


async def test_create_ok_and_detail(client, db):
    from .test_auth_login import register_and_login
    tokens = await register_and_login(client, email="cr@b.com")
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    body = {"name": "新测试线", "region": "测试区域", "sport": "hiking",
            "difficulty": 2, "distance_km": 5.0, "climb_m": 100,
            "start_lat": 30.0, "start_lon": 119.0}
    r = await client.post("/routes", json=body, headers=h)
    assert r.status_code == 201
    rid = r.json()["id"]
    r = await client.get(f"/routes/{rid}")
    assert r.status_code == 200 and r.json()["name"] == "新测试线"
    assert r.json()["elevation"] == [] and r.json()["warning"] is None


async def test_track_malformed_body_422(client, db):
    await seed_routes(db)
    r = await client.post("/routes/1/track", content=b"", headers={"Content-Type": "text/plain"})
    assert r.status_code == 422
