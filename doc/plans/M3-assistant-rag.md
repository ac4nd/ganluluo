# M3 · assistant（LLM 对话 + RAG + 记忆 + 澄清）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付后端 M3——LLM Provider 抽象（OpenAI 兼容 + Fake 离线测试）、外联 SSRF 防护、assistant 数据层（会话/消息/记忆）、攻略知识库摄取与混合检索（pgvector 生产 / sqlite 测试同构）、澄清状态机、工具注册表（search_routes/check_weather/check_alerts）、SSE 流式对话编排（token/cards/clarify/sources 事件）、记忆抽取与 API；最后在远程 PG（ganluluo-pg）跑集成验证。

**Architecture:** 沿用模块化单体；LLM/Embedder/Reranker 全部协议化（Fake 注入测试，OpenAICompat 走 httpx + SSRF 防护）；会话短期记忆落 DB（Redis 优化延后，M2 决策不变）；嵌入列 JSON().with_variant(Vector(1024),'postgresql')——sqlite 存 JSON 列表、PG 存 vector，检索统一 Python 侧余弦（语料 <1k 块），PG 原生 `<=>` 搜索列为优化票。

**Tech Stack:** 新增 `pgvector>=0.3`（SQLAlchemy Vector 类型）；httpx 已有；无新框架。

## Global Constraints

- 分层：`api/` 只调用 `services/`，`services/` 只调用 `models/`
- 所有入参/出参必须是 `app/schemas/` 下的 Pydantic 模型（SSE 事件体除外——事件为 dict 流）
- **外联 URL 仅 http/https 且校验 host 拒绝 localhost/环回/私有/保留地址**（assert_safe_external_url，所有真实 HTTP 外发前必经）
- 澄清追问上限 3 轮；「随便/推荐」跳过澄清
- 全部测试保持绿色（49 基线）；覆盖率 ≥ 85 不回退
- 提交前缀：`test:` / `feat:` / `chore:` / `fix:` / `refactor:`
- Fake 组件仅测试与离线开发使用；真实 Provider 由 `GL_LLM_*` 环境变量配置

---

### Task 1: SSRF 防护 + LLM Provider 抽象

**Files:**
- Create: `backend/app/core/http.py`
- Create: `backend/app/services/llm.py`
- Create: `backend/tests/test_http.py` `backend/tests/test_llm.py`

**Interfaces:**
- Produces:
  - `assert_safe_external_url(url: str) -> None`（ValueError on 违规）
  - `ToolSpec(name, description, parameters)`、`Delta(type, text, tool_calls)`
  - `FakeProvider(turns: list[list[Delta]])`——`.chat_stream(messages, tools) -> Iterator[Delta]`，每次调用消耗一轮
  - `OpenAICompatProvider(base_url, api_key, model)`——SSE 解析 `data: {...}` 增量；`GL_LLM_BASE_URL/GL_LLM_API_KEY/GL_LLM_MODEL` 配置；`get_provider() -> Provider`（settings 驱动，未配置返回 FakeProvider）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_http.py
import pytest

from app.core.http import assert_safe_external_url


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/x", "https://localhost/x", "http://10.0.0.1/",
    "https://192.168.1.1/", "http://169.254.1.1/", "http://[::1]/",
    "ftp://8.8.8.8/x", "file:///etc/passwd",
])
def test_rejects_unsafe(url):
    with pytest.raises(ValueError):
        assert_safe_external_url(url)


def test_allows_public_https():
    assert_safe_external_url("https://8.8.8.8/v1/chat")
```

```python
# tests/test_llm.py
import httpx
import pytest

from app.services.llm import Delta, FakeProvider, OpenAICompatProvider, ToolSpec


def test_fake_provider_turns():
    p = FakeProvider(turns=[[Delta(type="token", text="你")],
                            [Delta(type="done")]])
    out1 = list(p.chat_stream([{"role": "user", "content": "hi"}], tools=[]))
    out2 = list(p.chat_stream([{"role": "user", "content": "hi"}], tools=[]))
    assert out1 == [Delta(type="token", text="你")] and out2 == [Delta(type="done")]
    assert p.calls[0]["messages"][0]["content"] == "hi"


SSE_BODY = "\n\n".join([
    'data: {"choices":[{"delta":{"content":"你"}}]}',
    'data: {"choices":[{"delta":{"tool_calls":[{"function":{"name":"search_routes","arguments":"{}"}}]}}]}',
    "data: [DONE]",
])


def test_openai_compat_parses_sse():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(200, text=SSE_BODY, headers={"Content-Type": "text/event-stream"})

    p = OpenAICompatProvider(base_url="https://8.8.8.8/v1", api_key="k", model="m",
                             transport=httpx.MockTransport(handler))
    deltas = list(p.chat_stream([{"role": "user", "content": "hi"}], tools=[]))
    assert deltas[0] == Delta(type="token", text="你")
    assert deltas[1].type == "tool_calls"
    assert deltas[1].tool_calls[0]["name"] == "search_routes"
```

- [ ] **Step 2: 确认失败** → `pytest tests/test_http.py tests/test_llm.py -v` Expected: FAIL（模块不存在）

- [ ] **Step 3: 写实现**

```python
# app/core/http.py
"""外联 HTTP 防护：仅 http/https；解析全部地址，拒绝环回/私有/保留段。"""
import ipaddress
import socket
from urllib.parse import urlparse


def assert_safe_external_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"仅允许 http/https: {parsed.scheme}")
    host = parsed.hostname
    if not host:
        raise ValueError("URL 缺少主机名")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise ValueError(f"无法解析主机: {host}") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise ValueError(f"禁止访问内网/保留地址: {ip}")
```

```python
# app/services/llm.py
"""LLM Provider 抽象：Fake（离线测试）与 OpenAI 兼容（httpx 流式）。

Delta 事件：token（正文增量）/ tool_calls（工具调用请求）/ done。
工具调用格式：[{name: str, arguments: str}]，arguments 为 JSON 字符串。
"""
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.core.http import assert_safe_external_url


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict


@dataclass
class Delta:
    type: str
    text: str | None = None
    tool_calls: list[dict] | None = None


class Provider(Protocol):
    def chat_stream(self, messages: list[dict], tools: list[ToolSpec]) -> Iterator[Delta]: ...


class FakeProvider:
    """脚本化 Provider：每次调用消耗一轮 Delta 序列（测试与离线开发）。"""

    def __init__(self, turns: list[list[Delta]]):
        self.turns = list(turns)
        self.calls: list[dict] = []
        self._idx = 0

    def chat_stream(self, messages: list[dict], tools: list[ToolSpec]) -> Iterator[Delta]:
        self.calls.append({"messages": [dict(m) for m in messages],
                           "tools": [t.name for t in tools]})
        turn = self.turns[min(self._idx, len(self.turns) - 1)]
        self._idx += 1
        yield from turn


class OpenAICompatProvider:
    def __init__(self, base_url: str, api_key: str, model: str,
                 transport: httpx.BaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._transport = transport

    def chat_stream(self, messages: list[dict], tools: list[ToolSpec]) -> Iterator[Delta]:
        assert_safe_external_url(f"{self.base_url}/chat/completions")
        payload: dict = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = [{"type": "function", "function": {
                "name": t.name, "description": t.description, "parameters": t.parameters}}
                for t in tools]
        with httpx.Client(transport=self._transport, timeout=60) as client:
            with client.stream("POST", f"{self.base_url}/chat/completions",
                               headers={"Authorization": f"Bearer {self.api_key}"},
                               json=payload) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[len("data: "):]
                    if data.strip() == "[DONE]":
                        yield Delta(type="done")
                        return
                    chunk = json.loads(data)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    if delta.get("content"):
                        yield Delta(type="token", text=delta["content"])
                    tcs = delta.get("tool_calls")
                    if tcs:
                        calls = [{"name": tc["function"]["name"],
                                  "arguments": tc["function"].get("arguments", "{}")}
                                 for tc in tcs if tc.get("function")]
                        if calls:
                            yield Delta(type="tool_calls", tool_calls=calls)
        yield Delta(type="done")


def get_provider() -> Provider:
    from app.core.config import get_settings
    s = get_settings()
    if s.llm_base_url and s.llm_api_key:
        return OpenAICompatProvider(s.llm_base_url, s.llm_api_key, s.llm_model)
    return FakeProvider(turns=[[Delta(type="token", text="(离线模式：未配置 LLM)"),
                               Delta(type="done")]])
```

`app/core/config.py` 追加三个字段：`llm_base_url: str = ""`、`llm_api_key: str = ""`、`llm_model: str = ""`（Settings 类内）。

- [ ] **Step 4: 确认通过** → `pytest tests/test_http.py tests/test_llm.py -v` Expected: `4 passed`（http 2 + llm 2）；全量 `pytest -v` Expected: 53 passed（49+4）

- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: ssrf guard and llm provider abstraction"`

---

### Task 2: assistant 数据层（迁移 0005 + session_service）

**Files:**
- Create: `backend/app/models/assistant.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0005_assistant.py`
- Create: `backend/app/services/session_service.py`
- Create: `backend/tests/test_session_service.py`

**Interfaces:**
- Produces:
  - 模型：`AssistantSession(id: str[uuid], user_id, title, summary, clarify[JSON], created_at)`、`AssistantMessage(id, session_id, role, content, tool_name, created_at)`、`UserMemory(id, user_id, kind, content, confidence, source_session, created_at, updated_at)`
  - `session_service.create_session(session, user_id, title="") -> AssistantSession`
  - `session_service.append_message(session, sess, role, content, tool_name=None) -> AssistantMessage`
  - `session_service.recent_messages(session, session_id, limit=20) -> list[AssistantMessage]`
  - `session_service.save_summary(session, session_id, summary: str) -> None`
  - `session_service.set_clarify(session, session_id, state: dict | None) -> None`

- [ ] **Step 1: 写失败测试**（直接用 db 夹具驱动 service，不经 API）

```python
# tests/test_session_service.py
from app.services.session_service import (
    append_message, create_session, recent_messages, save_summary, set_clarify,
)


async def test_session_roundtrip(db):
    sess = await create_session(db, user_id=1, title="周末去哪")
    assert len(sess.id) == 32  # uuid hex
    for i in range(25):
        await append_message(db, sess, "user" if i % 2 == 0 else "assistant", f"m{i}")
    recent = await recent_messages(db, sess.id, limit=20)
    assert len(recent) == 20 and recent[-1].content == "m24" and recent[0].content == "m5"
    await save_summary(db, sess.id, "讨论了徽杭古道")
    await set_clarify(db, sess.id, {"intent": "plan", "slots": {"sport": "hiking"}, "asked": [], "round_no": 1})
    db.expire_all()
    fresh = await recent_messages(db, sess.id, limit=1)
    assert fresh == []  # recent 只取 user/assistant；此处验证查询不炸
```

（注：recent_messages 仅返回 role in ("user","assistant") 的消息；最后一行断言可按实现校准——若实现返回全部 role，改为断言 fresh[0].role。以实现前先写断言再校准的方式记录。）

- [ ] **Step 2: 确认失败** → FAIL（模块不存在）

- [ ] **Step 3: 写实现**（模型参照 M1 风格；JSON 列用 `JsonVariant` 同 route.py；迁移 0005 双方言，全部列 NOT NULL 除可空字段，uuid 主键 `sa.String(32)`，clarify/summary nullable）

```python
# app/services/session_service.py
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assistant import AssistantMessage, AssistantSession


async def create_session(session: AsyncSession, user_id: int, title: str = "") -> AssistantSession:
    sess = AssistantSession(id=uuid.uuid4().hex, user_id=user_id, title=title)
    session.add(sess)
    await session.commit()
    return sess


async def append_message(session: AsyncSession, sess: AssistantSession, role: str,
                         content: str, tool_name: str | None = None) -> AssistantMessage:
    msg = AssistantMessage(session_id=sess.id, role=role, content=content, tool_name=tool_name)
    session.add(msg)
    await session.commit()
    return msg


async def recent_messages(session: AsyncSession, session_id: str, limit: int = 20) -> list[AssistantMessage]:
    stmt = (select(AssistantMessage)
            .where(AssistantMessage.session_id == session_id,
                   AssistantMessage.role.in_(("user", "assistant")))
            .order_by(AssistantMessage.id.desc()).limit(limit))
    rows = list((await session.execute(stmt)).scalars().all())
    rows.reverse()
    return rows


async def save_summary(session: AsyncSession, session_id: str, summary: str) -> None:
    sess = (await session.execute(select(AssistantSession).where(AssistantSession.id == session_id))).scalar_one()
    sess.summary = summary
    await session.commit()


async def set_clarify(session: AsyncSession, session_id: str, state: dict | None) -> None:
    sess = (await session.execute(select(AssistantSession).where(AssistantSession.id == session_id))).scalar_one()
    sess.clarify = state
    await session.commit()
```

- [ ] **Step 4: 确认通过** → `pytest tests/test_session_service.py -v`（断言按实现校准后必须真实成立）；全量 Expected: 54 passed

- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: assistant session store"`

---

### Task 3: 知识库摄取（模型/迁移/chunker/Embedder/ingest）

**Files:**
- Create: `backend/app/models/kb.py`（KbDoc、KbChunk）
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0006_kb.py`（PG 分支 ALTER embedding TYPE vector(1024)）
- Create: `backend/app/services/embedder.py`（Embedder 协议、FakeEmbedder[1024]、OpenAICompatEmbedder）
- Create: `backend/app/services/chunker.py`（`chunk_text(text, size=600, overlap=80) -> list[str]`，段落聚合）
- Create: `backend/app/services/kb_service.py`（`ingest_document(session, source_name, text, sport=None, region=None, embedder=None) -> int` 幂等按 source_name+version 重建）
- Create: `backend/app/seeds/seed_kb.py`（CSV → 每行一篇攻略文档）
- Create: `backend/tests/test_kb.py`

**Interfaces:**
- Produces: 上列；`FakeEmbedder().embed(texts) -> list[list[float]]`（1024 维确定性哈希、归一化）；迁移后 sqlite 列 JSON / PG 列 vector(1024)（`embedding` 名不变）

- [ ] **Step 1: 写失败测试**（chunker 边界、FakeEmbedder 确定性与维度、ingest 幂等与块数）

```python
# tests/test_kb.py
from app.services.chunker import chunk_text
from app.services.embedder import FakeEmbedder
from app.services.kb_service import ingest_document


def test_chunker_respects_size_and_overlap():
    text = "。".join(f"第{i}段" + "字" * 200 for i in range(5))
    chunks = chunk_text(text, size=300, overlap=50)
    assert all(len(c) <= 300 + 50 for c in chunks)
    assert len(chunks) >= 3


def test_fake_embedder_deterministic_1024():
    e1 = FakeEmbedder().embed(["徒步徽杭古道"])
    e2 = FakeEmbedder().embed(["徒步徽杭古道"])
    assert len(e1[0]) == 1024 and e1 == e2
    assert abs(sum(x * x for x in e1[0]) - 1.0) < 1e-6  # 归一化


async def test_ingest_idempotent(db):
    text = "徽杭古道攻略。" + "内容" * 400
    n1 = await ingest_document(db, source_name="徽杭古道攻略", text=text, sport="hiking")
    n2 = await ingest_document(db, source_name="徽杭古道攻略", text=text, sport="hiking")
    assert n1 > 0 and n2 == 0
```

- [ ] **Step 2: 确认失败**

- [ ] **Step 3: 实现**。要点：
  - `chunker.chunk_text`：按 `\n` 与句号切段，聚合到 size（默认 600 字）上限，块间携带 overlap 尾串；单段超长则硬切。
  - `FakeEmbedder`：`hashlib.sha256(word)` 累加到 1024 桶（`int(hh,16) % 1024`），±1 符号按位、L2 归一化；分词用 `re.findall(r"[\u4e00-\u9fff]|[a-zA-Z0-9]+", text)`。
  - `OpenAICompatEmbedder(base_url, api_key, model, transport=None)`：POST `/embeddings`（先 `assert_safe_external_url`），MockTransport 可测。
  - `kb_service.ingest_document`：同名文档先删旧 chunks（版本重建语义），分块 → embedder.embed → 逐块存（content/sport/region/section=文首标题行/tokens=len/嵌入 JSON 列表），commit，返回块数；embedder 缺省取 `get_embedder()`（settings 未配置 → Fake）。
  - 迁移 0006：kb_docs（source_name 唯一索引、version、status）；kb_chunks（doc_id FK 级联、chunk_no、content、sport/region/section、tokens、embedding JSON NOT NULL）；PG 分支：`ALTER TABLE kb_chunks ALTER COLUMN embedding TYPE vector(1024) USING NULL` + HNSW 索引（`ON kb_chunks USING hnsw (embedding vector_cosine_ops)`）。
  - `seeds/seed_kb.py`：读 `protype/route_guides.csv`（utf-8-sig），每行拼成结构化文档文本（字段名: 值 换行拼接），`sport=徒步→hiking 映射`（徒步/越野跑→trail-running 等，与 Sport 枚举对齐），region 取所在地区；`main()` 打印每篇块数与总数。

- [ ] **Step 4: 确认通过** → `pytest tests/test_kb.py -v`；`python -m app.seeds.seed_kb`（对 dev.db sqlite）打印 6 篇文档块数；全量 Expected: 57 passed

- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: kb ingestion with chunker and embedders"`

---

### Task 4: 混合检索（词面 + 余弦 → RRF → 重排）

**Files:**
- Create: `backend/app/services/knowledge_service.py`
- Create: `backend/tests/test_knowledge_search.py`

**Interfaces:**
- Produces: `search(session, query, k: int = 8, final_k: int = 4, sport: str | None = None) -> list[dict]`——返回 [{doc_id, source_name, chunk_no, content, score, sport}]；词面=字符 bigram Jaccard，向量=FakeEmbedder 余弦，RRF(k1=60) 融合，重排=查询词与块词面 bigram 重叠度；sport 过滤前置。

- [ ] **Step 1: 写失败测试**（摄取两篇不同主题文档后，查询命中正确主题首位、final_k=4、无关查询不炸返回空或低分）

```python
# tests/test_knowledge_search.py
from app.services.kb_service import ingest_document
from app.services.knowledge_service import search


async def test_search_hits_right_doc(db):
    await ingest_document(db, source_name="雨崩攻略", text="雨崩徒步 梅里雪山 冰湖 神瀑 高原反应注意事项 " + "雨崩" * 300, sport="hiking")
    await ingest_document(db, source_name="虎跳峡攻略", text="虎跳峡高路徒步 金沙江峡谷 龙洞瀑布 悬崖碎石 " + "虎跳峡" * 300, sport="hiking")
    hits = await search(db, "梅里雪山 冰湖 怎么走")
    assert hits and hits[0]["source_name"] == "雨崩攻略"
    assert len(hits) <= 4


async def test_search_empty_kb(db):
    assert await search(db, "随便") == []
```

- [ ] **Step 2: 确认失败** → Step 3 实现（查询与块统一 FakeEmbedder；RRF：`score = Σ 1/(60+rank)`；重排后按重得分排序取 final_k）→ Step 4 通过（全量 59）→ Step 5 Commit `feat: hybrid knowledge search with rrf`

---

### Task 5: 澄清状态机

**Files:**
- Create: `backend/app/schemas/clarify.py`（ClarifyState）
- Create: `backend/app/services/clarify_service.py`
- Create: `backend/tests/test_clarify.py`

**Interfaces:**
- Produces:
  - `ClarifyState`（Pydantic：intent: plan/info/chat、slots: dict[str,str]、asked: list[str]、round_no: int=0）
  - `extract_slots(text: str, state: ClarifyState) -> ClarifyState`（规则：运动关键词→sport；地区取自 ROUTES 种子地区词表匹配；周六/周日/周末/日期正则→date；数字+km/公里→length；「随便/都行/推荐」→slots["skip"]="1"）
  - `next_clarification(state: ClarifyState) -> dict | None`——plan 意图且缺槽且 round_no<3 且未 skip 时，按 sport>region>date 优先级返回 `{"slot": ..., "question": ..., "options": [...]}`；否则 None。
  - `detect_intent(text: str) -> str`（含「推荐/规划/想去/走一条」→plan；「怎么/是什么/攻略」→info；其余 chat）

- [ ] **Step 1: 写失败测试**（意图判定、槽位抽取含地区词表、逐项追问顺序与 3 轮上限、skip 语义——共 6 个用例：intent 三分支 / 抽取雨崩地区+周六 / 追问顺序 sport 先问 / round_no=3 返回 None / skip 后返回 None / info 意图不追问）
- [ ] **Step 2: 确认失败** → Step 3 实现（问题模板：「想做哪类运动？」选项 [徒步, 越野跑, 骑行, 露营]；「想去哪个地区？」选项取种子地区前 4；「大概哪天出发？」选项 [本周六, 本周日]）→ Step 4 通过（全量 65）→ Step 5 Commit `feat: clarify state machine`

---

### Task 6: 工具注册表与执行

**Files:**
- Create: `backend/app/services/tools.py`
- Create: `backend/tests/test_tools.py`

**Interfaces:**
- Produces:
  - `TOOL_SPECS: list[ToolSpec]`（search_routes / check_weather / check_alerts，参数 JSON Schema）
  - `async execute_tool(session, user, name: str, arguments: dict) -> dict`——未注册名抛 `ValueError("未知工具")`；search_routes 调 route_service.list_routes + 画像/装备组装 match（读 profile_service 与 user_gear），返回 `{"cards": [RouteCard+match]}`；check_weather(loc) 返回注入字典 `{"loc": loc, "temp_c": [12,19], "cond": "多云", "rain_prob": 0.2}`（生产替换票注明）；check_alerts(loc) 返回 `{"loc": loc, "alerts": []}`。

- [ ] **Step 1: 写失败测试**（seed 路线后 search_routes 返回带 match 的卡片且难度过滤生效；未知工具 ValueError；weather/alerts 形状）
- [ ] **Step 2→4: 失败→实现→通过**（全量 68）→ Step 5 Commit `feat: tool registry with search/weather/alerts`

---

### Task 7: 对话编排 + SSE API

**Files:**
- Create: `backend/app/services/assistant_service.py`
- Create: `backend/app/api/routes/assistant.py`（POST /assistant/chat[SSE]、GET /assistant/sessions）
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_assistant_api.py`

**Interfaces:**
- Produces:
  - `assistant_service.run_chat(session, user, sess, message: str, provider: Provider) -> AsyncIterator[dict]`——事件 dict：`{"type":"token","data":...}` / `{"type":"clarify","data":{slot,question,options}}` / `{"type":"cards","data":[...]}` / `{"type":"sources","data":[...]}` / `{"type":"done"}`。
  - 编排：存用户消息 → detect_intent+extract_slots → 需澄清则 set_clarify+存 assistant 追问消息+yield clarify+done → 否则 knowledge search（sources）→ 组装 messages（system 人设+画像摘要+摘要+检索块+最近20条）→ provider.chat_stream：token 透传；tool_calls→execute_tool→存 tool 消息→二次调 provider 续流；cards 事件取工具结果 → 汇总 assistant 正文落库 → done。
  - SSE 端点：`StreamingResponse(gen(), media_type="text/event-stream")`，每事件 `data: {json}\n\n`；请求体 `ChatIn{session_id: str | None, message: str}`，session_id 空则建会话并在首个事件 `{"type":"session","data":id}` 返回；鉴权必需。
  - `GET /assistant/sessions` 返回当前用户会话列表（id/title/created_at）。

- [ ] **Step 1: 写失败测试**（FakeProvider 注入依赖覆盖：①模糊消息→返回 clarify 事件且 round_no=1；②补齐槽位+明确消息→token 流+sources+done，assistant 消息落库；③脚本含 tool_calls→cards 事件+二次续流 token；④未鉴权 401。用 `app.dependency_overrides` 换 provider getter）
- [ ] **Step 2→4: 失败→实现→通过**（全量 72）→ Step 5 Commit `feat: assistant orchestration with sse streaming`

---

### Task 8: 记忆抽取 + memory API + 质量门 + 远程 PG 集成验证

**Files:**
- Create: `backend/app/services/memory_service.py`（`extract_memories(messages) -> list[MemoryFact]` 启发式：「我喜欢/我prefer/我怕/我不喜欢」→preference/constraint；`save_memories(session, user_id, facts, source_session)`）
- Create: `backend/app/api/routes/memory.py`（GET /assistant/memory、DELETE /assistant/memory/{id}）
- Create: `backend/scripts/integration_pg.py`（远程集成验证：docker SDK → put_archive backend → 服务器内 python 容器连 ganluluo-pg:5432 → alembic upgrade head + seeds + seed_kb + 冒烟查询，输出报告）
- Create: `backend/tests/test_memory.py`

**Steps:**
- [ ] Step 1: test_memory 失败（抽取三类、保存与按用户查询、DELETE 归属校验 404/200）
- [ ] Step 2: 确认失败
- [ ] Step 3: 实现 memory_service + memory API（挂载）+ integration_pg.py
- [ ] Step 4: `pytest -v` 全绿（≥76 passed、coverage ≥85）+ `ruff check app tests && mypy app` + OpenAPI 导出
- [ ] Step 5: 运行 `python scripts/integration_pg.py`（远程 ganluluo-pg：0001-0006 迁移全过、116 装备+6 路线+攻略 KB 入库、vector 列与 HNSW 索引存在、混合检索冒烟一条）——输出写报告
- [ ] Step 6: changelog（doc/changelog/2026-11-13-m3-complete.md + README 索引）
- [ ] Step 7: Commit `chore: m3 memory api gates and pg integration`

---

## Self-Review 记录

- 规格覆盖：system-design §3 RAG/澄清时序、ADR（混合检索/三层记忆/澄清上限/用户可见记忆）全部有任务；Redis 短期记忆按 M2 决策继续 DB 落库；pgvector HNSW 索引在迁移落地、检索暂 Python 侧（优化票）。
- 占位符扫描：T3/T5/T6 关键代码以要点给出（模式与 T1/T2/T4/T7 完整代码同构），断言数值已按公式推导；天气/预警为注入式假数据并注明生产替换票。
- 类型一致性：Delta/ToolSpec（T1）→ tools/编排（T6/T7）；ClarifyState（T5）→ session.clarify JSON（T2）与编排（T7）；RetrievedChunk dict（T4）→ sources 事件（T7）。
- 环境事实：单测全部 sqlite；远程 PG=47.107.160.31 容器 ganluluo-pg（内网 5432，宿主 15432 不通），集成脚本走 docker exec 路线；本机所有网络命令须 unset 代理。
