import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.deps import get_current_admin
from app.models.user import User

from .test_auth_login import TEST_PW, register_and_login


def _admin() -> User:
    # 瞬态对象即可：get_current_admin 不触库（真实端点链路在 Task 4 验证）
    return User(email="a@b.com", nickname="管", is_admin=True)


def _plain() -> User:
    return User(email="p@b.com", nickname="晨", is_admin=False)


async def test_get_current_admin_allows_admin():
    admin = _admin()
    assert await get_current_admin(admin) is admin


async def test_get_current_admin_rejects_normal_403():
    with pytest.raises(HTTPException) as ei:
        await get_current_admin(_plain())
    assert ei.value.status_code == 403
    assert ei.value.detail == "需要管理员权限"


async def _disable(db, email: str) -> None:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    user.disabled = True
    await db.commit()


async def test_login_disabled_403(client, db):
    await register_and_login(client, email="dl@b.com")
    await _disable(db, "dl@b.com")
    r = await client.post("/auth/login", json={"email": "dl@b.com", "password": TEST_PW})
    assert r.status_code == 403
    assert r.json()["detail"] == "账号已禁用"


async def test_refresh_disabled_403(client, db):
    tokens = await register_and_login(client, email="rd@b.com")
    await _disable(db, "rd@b.com")
    r = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 403
    assert r.json()["detail"] == "账号已禁用"


async def test_disabled_user_with_valid_token_profile_403(client, db):
    tokens = await register_and_login(client, email="pd@b.com")
    await _disable(db, "pd@b.com")
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = await client.get("/profile", headers=h)
    assert r.status_code == 403
    assert r.json()["detail"] == "账号已禁用"
