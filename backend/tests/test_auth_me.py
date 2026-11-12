from .test_auth_login import register_and_login


async def test_me_ok(client):
    tokens = await register_and_login(client, email="m@b.com")
    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert r.status_code == 200 and r.json()["nickname"] == "晨"


async def test_me_without_token_401(client):
    r = await client.get("/auth/me")
    assert r.status_code == 401


async def test_me_refresh_token_rejected(client):
    tokens = await register_and_login(client, email="mr@b.com")
    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
    assert r.status_code == 401
