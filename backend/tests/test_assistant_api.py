"""对话编排 + SSE API：澄清流 / 直答流（检索）/ 工具调用流 / 鉴权。"""
import json

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.assistant.kb_service import ingest_document
from app.assistant.llm import Delta, FakeProvider
from app.assistant.router import assistant_provider
from app.assistant.session_store import recent_messages, save_summary
from app.core.db import get_session
from app.main import create_app
from app.models.assistant import AssistantMessage, AssistantSession
from app.seeds.seed_routes import seed_routes

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


async def test_clarify_flow(chat, db):
    """① 模糊 plan 消息 → clarify 事件追问 sport，轮数与已问槽位落库。"""
    app, client = chat
    app.dependency_overrides[assistant_provider] = lambda: FakeProvider(
        turns=[[Delta(type="done")]])
    tokens = await register_and_login(client, email="cl@b.com")
    r = await post_chat(client, tokens["access_token"], "想去个地方走走")
    assert r.status_code == 200
    events = parse_events(r.text)
    assert events[0]["type"] == "session"
    clarify = [e for e in events if e["type"] == "clarify"]
    assert clarify and clarify[0]["data"]["slot"] == "sport"
    assert clarify[0]["data"]["question"] == "想做哪类运动？"
    assert events[-1]["type"] == "done"
    row = await db.get(AssistantSession, events[0]["data"])
    assert row.clarify["round_no"] == 1 and row.clarify["asked"] == ["sport"]
    msgs = await recent_messages(db, row.id)
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[-1].content == "想做哪类运动？"


async def test_clarify_chain_survives_bare_answer(chat, db):
    """澄清进行中同会话裸回答「徒步」→ 不终止追问链：补 sport 槽后继续 clarify region。"""
    app, client = chat
    provider = FakeProvider(turns=[[Delta(type="done")]])
    app.dependency_overrides[assistant_provider] = lambda: provider
    tokens = await register_and_login(client, email="bc@b.com")
    token = tokens["access_token"]
    r1 = await post_chat(client, token, "想去个地方走走")
    assert r1.status_code == 200
    events1 = parse_events(r1.text)
    assert events1[0]["type"] == "session"
    clarify1 = [e for e in events1 if e["type"] == "clarify"]
    assert clarify1 and clarify1[0]["data"]["slot"] == "sport"

    session_id = events1[0]["data"]
    r2 = await post_chat(client, token, "徒步", session_id=session_id)
    assert r2.status_code == 200
    events2 = parse_events(r2.text)
    # 裸回答只补槽位，追问链继续（region），不进入答题分支（无 token、provider 未被调用）
    assert not any(e["type"] == "session" for e in events2)
    assert not any(e["type"] == "token" for e in events2)
    assert not provider.calls
    clarify2 = [e for e in events2 if e["type"] == "clarify"]
    assert clarify2 and clarify2[0]["data"]["slot"] == "region"
    assert clarify2[0]["data"]["question"] == "想去哪个地区？"
    assert events2[-1]["type"] == "done"
    row = await db.get(AssistantSession, session_id)
    assert row.clarify["round_no"] == 2
    assert row.clarify["intent"] == "plan"
    assert row.clarify["slots"]["sport"] == "hiking"
    assert row.clarify["asked"] == ["sport", "region"]


async def test_direct_answer_flow(chat, db):
    """② 槽位齐全的明确消息 → sources + token 流 + done，assistant 正文落库。"""
    app, client = chat
    await ingest_document(
        db, source_name="雨崩攻略",
        text="雨崩徒步路线：从西当村进山，经尼农大峡谷抵达雨崩上村，次日徒步神瀑往返。" * 5,
        sport="hiking")
    app.dependency_overrides[assistant_provider] = lambda: FakeProvider(
        turns=[[Delta(type="token", text="从西当进山"), Delta(type="done")]])
    tokens = await register_and_login(client, email="da@b.com")
    r = await post_chat(client, tokens["access_token"], "雨崩徒步怎么走，周六出发")
    assert r.status_code == 200
    events = parse_events(r.text)
    types = [e["type"] for e in events]
    assert types[0] == "session" and types[-1] == "done"
    sources = [e for e in events if e["type"] == "sources"]
    assert sources and sources[0]["data"][0]["source_name"] == "雨崩攻略"
    assert "chunk_no" in sources[0]["data"][0]
    streamed = "".join(e["data"] for e in events if e["type"] == "token")
    assert streamed == "从西当进山"
    msgs = await recent_messages(db, events[0]["data"])
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert msgs[-1].content == "从西当进山"
    # 会话列表可见，标题取自首条消息
    r2 = await client.get("/assistant/sessions",
                          headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert r2.status_code == 200
    listed = r2.json()
    assert [s["id"] for s in listed] == [events[0]["data"]]
    assert listed[0]["title"] == "雨崩徒步怎么走，周六出发"
    assert listed[0]["created_at"]


async def test_tool_call_flow(chat, db):
    """③ 脚本含 tool_calls → cards 事件 + 工具结果落库 + 二次续流 token。"""
    app, client = chat
    await seed_routes(db)
    provider = FakeProvider(turns=[
        [Delta(type="tool_calls", tool_calls=[
            {"name": "search_routes", "arguments": '{"sport":"hiking"}'}]),
         Delta(type="done")],
        [Delta(type="token", text="为你找到"), Delta(type="done")],
    ])
    app.dependency_overrides[assistant_provider] = lambda: provider
    tokens = await register_and_login(client, email="tc@b.com")
    r = await post_chat(client, tokens["access_token"], "推荐周六去雨崩徒步")
    assert r.status_code == 200
    events = parse_events(r.text)
    cards = [e for e in events if e["type"] == "cards"]
    assert cards and cards[0]["data"] and cards[0]["data"][0]["name"]
    assert any(e["type"] == "token" and e["data"] == "为你找到" for e in events)
    assert events[-1]["type"] == "done"
    assert len(provider.calls) == 2  # 工具执行后二次续流
    tool_rows = (await db.execute(
        select(AssistantMessage).where(AssistantMessage.role == "tool"))).scalars().all()
    assert tool_rows and tool_rows[0].tool_name == "search_routes"
    assert json.loads(tool_rows[0].content)["cards"]


async def test_chat_requires_auth(chat):
    """④ 未带令牌 → 401。"""
    _app, client = chat
    r = await client.post("/assistant/chat", json={"session_id": None, "message": "你好"})
    assert r.status_code == 401
    r2 = await client.get("/assistant/sessions")
    assert r2.status_code == 401


async def test_chat_reuses_existing_session(chat, db):
    """携带 session_id 复用会话：不再发 session 事件，消息进入同一会话。"""
    app, client = chat
    provider = FakeProvider(turns=[[Delta(type="token", text="你好呀"), Delta(type="done")]])
    app.dependency_overrides[assistant_provider] = lambda: provider
    tokens = await register_and_login(client, email="ru@b.com")
    token = tokens["access_token"]
    first = parse_events((await post_chat(client, token, "你好呀")).text)
    session_id = first[0]["data"]
    await save_summary(db, session_id, "用户在了解入门路线")
    second = parse_events((await post_chat(client, token, "再聊聊", session_id=session_id)).text)
    assert not any(e["type"] == "session" for e in second)
    assert second[-1]["type"] == "done"
    # 二次对话的 system 上下文携带会话摘要与用户画像
    assert "会话摘要：用户在了解入门路线" in provider.calls[1]["messages"][0]["content"]
    assert "用户画像" in provider.calls[1]["messages"][0]["content"]
    msgs = await recent_messages(db, session_id)
    assert [m.role for m in msgs] == ["user", "assistant", "user", "assistant"]

    r404 = await client.post(
        "/assistant/chat", json={"session_id": "nope", "message": "hi"},
        headers={"Authorization": f"Bearer {token}"})
    assert r404.status_code == 404


async def test_tool_bad_arguments_fallback(chat, db):
    """arguments 非法/非对象 → 容错为空参继续；未知工具 → 错误结果落库为 tool 消息。"""
    app, client = chat
    await seed_routes(db)
    provider = FakeProvider(turns=[
        [Delta(type="tool_calls", tool_calls=[
            {"name": "search_routes", "arguments": "not-json"},
            {"name": "nope_tool", "arguments": "{}"},
            {"name": "check_weather", "arguments": "[1,2]"}]),  # 合法 JSON 但非对象
         Delta(type="done")],
        [Delta(type="token", text="收到"), Delta(type="done")],
    ])
    app.dependency_overrides[assistant_provider] = lambda: provider
    tokens = await register_and_login(client, email="fb@b.com")
    r = await post_chat(client, tokens["access_token"], "随便推荐一条")
    assert r.status_code == 200
    events = parse_events(r.text)
    # not-json 容错为 {} → search_routes 返回全部已发布路线
    assert any(e["type"] == "cards" and e["data"] for e in events)
    assert events[-1]["type"] == "done"
    tool_rows = (await db.execute(
        select(AssistantMessage).where(AssistantMessage.role == "tool")
        .order_by(AssistantMessage.id))).scalars().all()
    assert len(tool_rows) == 3
    assert "error" in json.loads(tool_rows[1].content)  # 未知工具
    assert "error" in json.loads(tool_rows[2].content)  # check_weather 缺 loc
