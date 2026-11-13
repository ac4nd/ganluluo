from .test_auth_login import register_and_login


async def _auth_headers(client, email="p@b.com"):
    tokens = await register_and_login(client, email=email)
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_get_default_profile(client):
    h = await _auth_headers(client)
    r = await client.get("/profile", headers=h)
    assert r.status_code == 200
    assert r.json() == {"sports": [], "exp_level": 1, "fitness": 2}


async def test_put_and_get_profile(client):
    h = await _auth_headers(client, email="p2@b.com")
    body = {"sports": ["hiking", "stream"], "exp_level": 3, "fitness": 3}
    r = await client.put("/profile", json=body, headers=h)
    assert r.status_code == 200 and r.json()["sports"] == ["hiking", "stream"]
    r = await client.get("/profile", headers=h)
    assert r.json()["fitness"] == 3


async def test_put_invalid_fitness_422(client):
    h = await _auth_headers(client, email="p3@b.com")
    r = await client.put("/profile", json={"sports": ["hiking"], "exp_level": 1, "fitness": 9}, headers=h)
    assert r.status_code == 422
