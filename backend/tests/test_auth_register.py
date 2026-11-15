from .test_auth_login import TEST_PW


async def test_register_ok(client):
    r = await client.post("/auth/register", json={
        "email": "a@b.com", "password": TEST_PW, "nickname": "晨风"})
    assert r.status_code == 201
    assert r.json()["nickname"] == "晨风"


async def test_register_duplicate_409(client):
    body = {"email": "a@b.com", "password": TEST_PW, "nickname": "晨风"}
    await client.post("/auth/register", json=body)
    r = await client.post("/auth/register", json=body)
    assert r.status_code == 409


async def test_register_missing_identity_422(client):
    r = await client.post("/auth/register", json={"password": TEST_PW, "nickname": "晨风"})
    assert r.status_code == 422
