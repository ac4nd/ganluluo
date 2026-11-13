from app.seeds.seed_routes import seed_routes

from .test_track_service import GPX


async def test_list_with_filters(client, db):
    await seed_routes(db)
    r = await client.get("/routes", params={"sport": "hiking", "difficulty_max": 3})
    assert r.status_code == 200
    names = {x["name"] for x in r.json()}
    assert "虎跳峡高路徒步（一日精华段）" in names
    assert "五台山顺朝（三天两夜大朝台）" not in names


async def test_get_detail(client, db):
    await seed_routes(db)
    r = await client.get("/routes/1")
    assert r.status_code == 200
    body = r.json()
    assert body["name"].startswith("雨崩")
    assert isinstance(body["elevation"], list)


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
