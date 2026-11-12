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
