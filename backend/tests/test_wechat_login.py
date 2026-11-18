"""M8 Task 1：POST /auth/wechat-login 微信一键登录。

凭据纪律：无真实 appid/secret 字面量（测试值拼接构造，如 "wx"+"testappid"）。
monkeypatch 点：service 层 app.domains.auth.service.jscode2session——httpx 外联
收在该函数内，patch 它即离线覆盖真实路径，且 assert_safe_external_url 的 DNS
解析不进测试路径（离线环境确定性通过）。
"""

import hashlib
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.domains.auth import service as user_service
from app.models.user import User

# 假凭据（拼接构造，避免静态扫描误报）
FAKE_APPID = "wx" + "testappid"
FAKE_SECRET = "test" + "secret"


@pytest.fixture
def wechat_off(monkeypatch):
    """未配置微信凭据：env 变量优先于 .env 文件，显式置空保证分支判定稳定。"""
    monkeypatch.setenv("GL_WECHAT_APPID", "")
    monkeypatch.setenv("GL_WECHAT_SECRET", "")
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


@pytest.fixture
def wechat_on(monkeypatch):
    """凭据齐全（假值）→ 走真实路径分支。"""
    monkeypatch.setenv("GL_WECHAT_APPID", FAKE_APPID)
    monkeypatch.setenv("GL_WECHAT_SECRET", FAKE_SECRET)
    get_settings.cache_clear()
    yield
    monkeypatch.undo()
    get_settings.cache_clear()


async def _me(client, tokens: dict) -> dict:
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = await client.get("/auth/me", headers=h)
    assert r.status_code == 200
    return r.json()


# ---------- mock 路径（未配置 + dev） ----------


async def test_mock_new_user_tokenpair_usable(client, wechat_off, db):
    r = await client.post("/auth/wechat-login", json={"code": "mock-code-1"})
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"] and body["refresh_token"] and body["token_type"] == "bearer"
    me = await _me(client, body)
    # 缺省昵称"徒步者"+4 位数字；oauth 用户无 email/phone
    assert me["nickname"].startswith("徒步者") and len(me["nickname"]) == 7
    assert me["email"] is None and me["phone"] is None
    # oauth 落库：openid 为确定性 mock 哈希
    openid = "wxmock_" + hashlib.sha256(b"mock-code-1").hexdigest()[:24]
    user = (
        await db.execute(
            select(User).where(User.oauth_provider == "wechat", User.oauth_subject == openid)
        )
    ).scalar_one()
    assert user.id == me["id"]


async def test_mock_same_code_same_user_different_code_new_user(client, wechat_off):
    t1 = (await client.post("/auth/wechat-login", json={"code": "stable-code"})).json()
    u1 = await _me(client, t1)
    t2 = (await client.post("/auth/wechat-login", json={"code": "stable-code"})).json()
    u2 = await _me(client, t2)
    assert u1["id"] == u2["id"]  # 确定性复用：同 code 同用户
    t3 = (await client.post("/auth/wechat-login", json={"code": "other-code"})).json()
    u3 = await _me(client, t3)
    assert u3["id"] != u1["id"]


async def test_mock_nickname_passthrough(client, wechat_off):
    tokens = (
        await client.post("/auth/wechat-login", json={"code": "nick-code", "nickname": "山雀"})
    ).json()
    assert (await _me(client, tokens))["nickname"] == "山雀"


async def test_code_and_nickname_validation(client, wechat_off):
    assert (await client.post("/auth/wechat-login", json={"code": ""})).status_code == 422
    assert (await client.post("/auth/wechat-login", json={"code": "x" * 129})).status_code == 422
    assert (
        await client.post("/auth/wechat-login", json={"code": "ok", "nickname": "n" * 33})
    ).status_code == 422


async def test_soft_deleted_oauth_user_relogins_as_new_row(client, wechat_off, db):
    tokens = (await client.post("/auth/wechat-login", json={"code": "del-code"})).json()
    old_id = (await _me(client, tokens))["id"]
    user = await db.get(User, old_id)
    user.deleted_at = datetime.now(UTC)
    await db.commit()
    r = await client.post("/auth/wechat-login", json={"code": "del-code"})
    assert r.status_code == 200  # 软删除用户视为不存在：另起新号而非 404/401
    assert (await _me(client, r.json()))["id"] != old_id


async def test_disabled_oauth_user_403(client, wechat_off, db):
    tokens = (await client.post("/auth/wechat-login", json={"code": "dis-code"})).json()
    user = await db.get(User, (await _me(client, tokens))["id"])
    user.disabled = True
    await db.commit()
    r = await client.post("/auth/wechat-login", json={"code": "dis-code"})
    assert r.status_code == 403 and r.json()["detail"] == "账号已禁用"


# ---------- prod 未配置 ----------


async def test_prod_unconfigured_503(client, monkeypatch):
    monkeypatch.setenv("GL_ENV", "prod")
    monkeypatch.setenv("GL_WECHAT_APPID", "")
    monkeypatch.setenv("GL_WECHAT_SECRET", "")
    get_settings.cache_clear()
    try:
        r = await client.post("/auth/wechat-login", json={"code": "c"})
        assert r.status_code == 503 and r.json()["detail"] == "微信登录未配置"
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


# ---------- 真实路径（配置齐全；patch service 层 jscode2session） ----------


async def test_real_path_errcode_401(client, wechat_on, monkeypatch):
    async def fake_jscode(appid: str, secret: str, code: str) -> dict:
        assert appid == FAKE_APPID and secret == FAKE_SECRET and code == "bad-code"
        return {"errcode": 40029, "errmsg": "invalid code"}

    monkeypatch.setattr(user_service, "jscode2session", fake_jscode)
    r = await client.post("/auth/wechat-login", json={"code": "bad-code"})
    assert r.status_code == 401 and r.json()["detail"] == "微信登录失败"


async def test_real_path_missing_openid_401(client, wechat_on, monkeypatch):
    async def fake_jscode(appid: str, secret: str, code: str) -> dict:
        return {"session_key": "sk"}  # 无 errcode 也无 openid → 同样拒绝

    monkeypatch.setattr(user_service, "jscode2session", fake_jscode)
    r = await client.post("/auth/wechat-login", json={"code": "weird"})
    assert r.status_code == 401


async def test_real_path_upstream_down_502(client, wechat_on, monkeypatch):
    async def boom(appid: str, secret: str, code: str) -> dict:
        raise user_service.WechatUpstreamError("connect timeout")

    monkeypatch.setattr(user_service, "jscode2session", boom)
    r = await client.post("/auth/wechat-login", json={"code": "real-code"})
    assert r.status_code == 502 and r.json()["detail"] == "微信服务不可达"


async def test_real_path_openid_creates_oauth_user(client, wechat_on, monkeypatch, db):
    async def fake_jscode(appid: str, secret: str, code: str) -> dict:
        return {"openid": "oX-123", "session_key": "sk"}

    monkeypatch.setattr(user_service, "jscode2session", fake_jscode)
    tokens = (await client.post("/auth/wechat-login", json={"code": "real"})).json()
    me = await _me(client, tokens)
    user = (await db.execute(select(User).where(User.oauth_subject == "oX-123"))).scalar_one()
    assert user.oauth_provider == "wechat" and user.id == me["id"]
