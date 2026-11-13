from app.seeds.seed_gear import seed

from .test_auth_login import register_and_login


async def test_put_get_replace(client, db):
    await seed(db)
    tokens = await register_and_login(client, email="g@b.com")
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = await client.put("/gear-list", json={"items": [
        {"item_key": "boots", "model_id": 1}, {"item_key": "poles", "model_id": 7}]}, headers=h)
    assert r.status_code == 200 and len(r.json()) == 2
    # 整表替换语义：第二次 PUT 覆盖第一次
    r = await client.put("/gear-list", json={"items": [{"item_key": "shell", "model_id": 30}]}, headers=h)
    assert len(r.json()) == 1 and r.json()[0]["item_key"] == "shell"


async def test_put_requires_auth(client):
    r = await client.put("/gear-list", json={"items": []})
    assert r.status_code == 401


def _boots_model_id(catalog: dict) -> int:
    # model_id must reference a real gear_models row: resolve it from the
    # catalog instead of assuming a fixed autoincrement id.
    return next(m["id"] for it in catalog["items"] if it["key"] == "boots" for m in it["models"])


async def test_get_gear_list(client, db):
    await seed(db)
    tokens = await register_and_login(client, email="gl@b.com")
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    boots_id = _boots_model_id((await client.get("/gear/catalog")).json())
    await client.put("/gear-list", json={"items": [{"item_key": "boots", "model_id": boots_id}]}, headers=h)
    r = await client.get("/gear-list", headers=h)
    assert r.status_code == 200
    assert len(r.json()) == 1 and r.json()[0]["item_key"] == "boots" and r.json()[0]["model_id"] == boots_id


async def test_get_requires_auth(client):
    r = await client.get("/gear-list")
    assert r.status_code == 401


async def test_put_rejects_unknown_item_key(client, db):
    await seed(db)
    tokens = await register_and_login(client, email="k@b.com")
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    boots_id = _boots_model_id((await client.get("/gear/catalog")).json())
    await client.put("/gear-list", json={"items": [{"item_key": "boots", "model_id": boots_id}]}, headers=h)
    r = await client.put("/gear-list", json={"items": [{"item_key": "jetpack"}]}, headers=h)
    assert r.status_code == 422 and "未知装备类型" in r.json()["detail"]
    # 校验先于替换：坏载荷不得清空已有列表（原先会 500 且列表已被删）
    r = await client.get("/gear-list", headers=h)
    assert [it["item_key"] for it in r.json()] == ["boots"]


async def test_put_rejects_unknown_model_id_and_duplicates(client, db):
    await seed(db)
    tokens = await register_and_login(client, email="d@b.com")
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = await client.put("/gear-list", json={"items": [{"item_key": "boots", "model_id": 999999}]}, headers=h)
    assert r.status_code == 422 and "未知型号" in r.json()["detail"]
    r = await client.put("/gear-list", json={"items": [{"item_key": "boots"}, {"item_key": "boots"}]}, headers=h)
    assert r.status_code == 422 and "重复条目" in r.json()["detail"]
