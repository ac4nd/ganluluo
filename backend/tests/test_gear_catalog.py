from app.seeds.seed_gear import seed


async def test_catalog_after_seed(client, db):
    await seed(db)
    r = await client.get("/gear/catalog")
    assert r.status_code == 200
    body = r.json()
    keys = {i["key"] for i in body["items"]}
    assert {"boots", "snowboard", "ski"} <= keys
    assert len(body["categories"]) == 8
    boots = next(i for i in body["items"] if i["key"] == "boots")
    assert any(m["brand"] == "Salomon" for m in boots["models"])


async def test_catalog_idempotent_seed(client, db):
    n1 = await seed(db)
    n2 = await seed(db)
    assert n2 == 0
