"""配额执行 API：日额度拦截（quota_exceeded + done）、正常流写 llm_usage、per-user 短窗限流 429。"""
import json

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.assistant.llm import Delta, FakeProvider
from app.assistant.router import assistant_provider
from app.assistant.session_store import create_session
from app.core.db import get_session
from app.core.security import decode_token
from app.domains.admin.quota_service import record_usage
from app.main import create_app
from app.models.assistant import AssistantMessage
from app.models.quota import LlmUsage

from .test_auth_login import register_and_login


def parse_events(body: str) -> list[dict]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


@pytest_asyncio.fixture
async def chat(db):
    """(app, client)：db 会话已覆盖，provider 由各测试自行覆盖注入。"""
    app = create_app()

    async def override():
        yield db

    app.dependency_overrides[get_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield app, c


async def post_chat(client, token: str, message: str, session_id: str | None = None):
    return await client.post(
        "/assistant/chat",
        json={"session_id": session_id, "message": message},
        headers={"Authorization": f"Bearer {token}"},
    )


async def test_chat_blocked_when_daily_quota_exhausted(chat, db):
    """trial 档 5 次用满（allowed 严格 <）→ 第 6 次请求 quota_exceeded：消息不落库、provider 不被调用。"""
    app, client = chat
    provider = FakeProvider(turns=[[Delta(type="token", text="不应生成"), Delta(type="done")]])
    app.dependency_overrides[assistant_provider] = lambda: provider
    tokens = await register_and_login(client, email="qblock@b.com")
    user_id = int(decode_token(tokens["access_token"])["sub"])
    # 直接调 service 造满当日 5 次 chat 用量（token 750 远低于 20000，单独验证 chats 维度）
    for _ in range(5):
        await record_usage(db, user_id, "seed-s1", "m", 100, 50)
    # 预建会话复用：跳过 session 事件，事件序列恰为 [quota_exceeded, done]
    sess = await create_session(db, user_id, title="预建会话")

    r = await post_chat(client, tokens["access_token"], "你好", session_id=sess.id)
    assert r.status_code == 200
    events = parse_events(r.text)
    assert [e["type"] for e in events] == ["quota_exceeded", "done"]
    data = events[0]["data"]
    assert data["tier"] == "trial"
    assert data["daily_chats_used"] == 5 and data["daily_chats_limit"] == 5
    assert data["reset_at"] == "明天 00:00"
    # 消息未落库（配额闸门在 append_message 之前）
    count = (await db.execute(select(func.count()).select_from(AssistantMessage))).scalar()
    assert count == 0
    assert not provider.calls


async def test_chat_writes_usage_when_allowed(chat, db):
    """未超额：正常 token 流不变，流结束写 1 条 llm_usage（pt/ct 按 len//2 估算均 > 0）。"""
    app, client = chat
    app.dependency_overrides[assistant_provider] = lambda: FakeProvider(
        turns=[[Delta(type="token", text="为你介绍路线"), Delta(type="done")]])
    tokens = await register_and_login(client, email="qok@b.com")
    r = await post_chat(client, tokens["access_token"], "你好")
    assert r.status_code == 200
    events = parse_events(r.text)
    types = [e["type"] for e in events]
    assert types[0] == "session" and types[-1] == "done"
    assert not any(e["type"] == "quota_exceeded" for e in events)
    streamed = "".join(e["data"] for e in events if e["type"] == "token")
    assert streamed == "为你介绍路线"

    user_id = int(decode_token(tokens["access_token"])["sub"])
    rows = (await db.execute(
        select(LlmUsage).where(LlmUsage.user_id == user_id))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.session_id == events[0]["data"]
    assert row.prompt_tokens > 0 and row.completion_tokens > 0
    assert row.total_tokens == row.prompt_tokens + row.completion_tokens


async def test_chat_rate_limited_429(chat):
    """per-user 短窗限流：同用户第 6 次请求 429（slowapi 在端点执行前拦截，SSE 未开始）。"""
    app, client = chat
    app.dependency_overrides[assistant_provider] = lambda: FakeProvider(
        turns=[[Delta(type="token", text="好的"), Delta(type="done")]])
    tokens = await register_and_login(client, email="qrate@b.com")
    token = tokens["access_token"]
    statuses = [(await post_chat(client, token, f"第{i}次聊天")).status_code for i in range(6)]
    assert statuses == [200, 200, 200, 200, 200, 429]
