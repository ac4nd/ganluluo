async def register_and_login(client, email="l@b.com"):
    await client.post("/auth/register", json={"email": email, "password": "passw0rd!", "nickname": "晨"})
    r = await client.post("/auth/login", json={"email": email, "password": "passw0rd!"})
    assert r.status_code == 200
    return r.json()


async def test_login_ok_and_tokens(client):
    tokens = await register_and_login(client)
    assert tokens["access_token"] and tokens["refresh_token"]


async def test_login_wrong_password_401(client):
    await client.post("/auth/register", json={"email": "w@b.com", "password": "passw0rd!", "nickname": "晨"})
    r = await client.post("/auth/login", json={"email": "w@b.com", "password": "wrong!"})
    assert r.status_code == 401


async def test_refresh_rotation_and_reuse_detection(client):
    tokens = await register_and_login(client, email="r@b.com")
    r1 = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r1.status_code == 200
    # 复用旧 refresh → 401 且全部会话吊销
    r2 = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r2.status_code == 401
    r3 = await client.post("/auth/refresh", json={"refresh_token": r1.json()["refresh_token"]})
    assert r3.status_code == 401


async def test_logout_revokes(client):
    tokens = await register_and_login(client, email="o@b.com")
    await client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    r = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401
