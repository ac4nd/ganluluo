from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.models.route import Route
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


# ---------- M8.6：created_after 时间过滤 + sort 排序 ----------


async def test_created_after_filters_old_route(client, db):
    """手动把 route 2 的 created_at 改到 30 天前；created_after=今天只回新线。"""
    await seed_routes(db)
    days_ago = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
    await db.execute(update(Route).where(Route.id == 2).values(created_at=days_ago))
    await db.commit()
    today = datetime.now(UTC).date().isoformat()
    r = await client.get("/routes", params={"created_after": today})
    assert r.status_code == 200
    ids = {x["id"] for x in r.json()}
    assert 1 in ids and 2 not in ids


async def test_created_after_old_date_combines_with_region(client, db):
    """下界早于所有路线时不过滤，且可与既有 region 参数叠加。"""
    await seed_routes(db)
    r = await client.get("/routes", params={"created_after": "2020-01-01", "region": "云南"})
    assert r.status_code == 200
    assert {x["id"] for x in r.json()} == {1, 2}


async def test_sort_new_desc(client, db):
    """sort=new 按 created_at 降序：显式把 6 条种子线错开（id 越大越新）。"""
    await seed_routes(db)
    now = datetime.now(UTC).replace(tzinfo=None)
    for i in range(1, 7):
        await db.execute(update(Route).where(Route.id == i)
                         .values(created_at=now - timedelta(minutes=10 - i)))
    await db.commit()
    r = await client.get("/routes", params={"sort": "new"})
    assert r.status_code == 200
    assert [x["id"] for x in r.json()] == [6, 5, 4, 3, 2, 1]


async def test_sort_points_tracked_route_first(client, db):
    """sort=points：上传过轨迹（5 点）的 route 1 排最前，无轨迹种子线排后。"""
    await seed_routes(db)
    r = await client.post("/routes/1/track", content=GPX.encode(), headers={"Content-Type": "text/plain"})
    assert r.status_code == 200
    r = await client.get("/routes", params={"sort": "points"})
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()]
    assert ids[0] == 1
    assert set(ids) == set(range(1, 7))  # 全量仍在，只是排序变化


async def test_created_after_bad_format_422(client, db):
    r = await client.get("/routes", params={"created_after": "2026/01/02"})
    assert r.status_code == 422
    assert r.json()["detail"] == "时间格式应为 YYYY-MM-DD"


async def test_sort_invalid_value_422(client, db):
    r = await client.get("/routes", params={"sort": "hot"})
    assert r.status_code == 422
    assert r.json()["detail"] == "非法排序方式"


# ---------- M8.7 I-1：limit/offset 分页（1141 条实化后移动端限量拉取） ----------


async def test_limit_returns_subset(client, db):
    """limit=3 只回前 3 条（默认 id 升序），默认 limit=50 下 6 条种子不受影响。"""
    await seed_routes(db)
    r = await client.get("/routes", params={"limit": 3})
    assert r.status_code == 200
    assert [x["id"] for x in r.json()] == [1, 2, 3]


async def test_offset_pages_disjoint(client, db):
    """limit=3 offset=0/3 两页连续无重叠：合起来即全量 6 条。"""
    await seed_routes(db)
    p1 = (await client.get("/routes", params={"limit": 3, "offset": 0})).json()
    p2 = (await client.get("/routes", params={"limit": 3, "offset": 3})).json()
    assert [x["id"] for x in p1] == [1, 2, 3]
    assert [x["id"] for x in p2] == [4, 5, 6]
    assert not ({x["id"] for x in p1} & {x["id"] for x in p2})


async def test_limit_zero_422(client, db):
    """limit=0 违反 ge=1 约束 → FastAPI 422。"""
    r = await client.get("/routes", params={"limit": 0})
    assert r.status_code == 422


async def test_offset_beyond_end_returns_empty(client, db):
    """offset 越界返回空数组而非报错（前端据此判定 hasMore=False）。"""
    await seed_routes(db)
    r = await client.get("/routes", params={"limit": 20, "offset": 100})
    assert r.status_code == 200
    assert r.json() == []


async def test_sort_points_paginates_after_python_sort(client, db):
    """sort=points：全量 python 排序后切页，跨页顺序仍连续（第一页头一条是有轨迹的 route 1）。"""
    await seed_routes(db)
    r = await client.post("/routes/1/track", content=GPX.encode(),
                          headers={"Content-Type": "text/plain"})
    assert r.status_code == 200
    p1 = (await client.get("/routes", params={"sort": "points", "limit": 2})).json()
    p2 = (await client.get("/routes", params={"sort": "points", "limit": 2, "offset": 2})).json()
    assert [x["id"] for x in p1] == [1, 2]
    assert [x["id"] for x in p2] == [3, 4]
    assert not ({x["id"] for x in p1} & {x["id"] for x in p2})


async def test_service_list_routes_default_no_pagination(db):
    """service 层 limit 缺省不分页：assistant 检索（tools.search_routes_for）
    依赖全量候选集，HTTP 默认页大小不能下沉到 service。"""
    await seed_routes(db)
    from app.domains.sports import route_service
    rows = await route_service.list_routes(db)
    assert len(rows) == 6
