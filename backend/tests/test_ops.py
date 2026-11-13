async def test_health(client):
    r = await client.get("/ops/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
