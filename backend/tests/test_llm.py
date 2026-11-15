# tests/test_llm.py
import json

import httpx

from app.assistant.llm import Delta, FakeProvider, OpenAICompatProvider


async def test_fake_provider_turns():
    p = FakeProvider(turns=[[Delta(type="token", text="你")],
                            [Delta(type="done")]])
    out1 = [d async for d in p.chat_stream([{"role": "user", "content": "hi"}], tools=[])]
    out2 = [d async for d in p.chat_stream([{"role": "user", "content": "hi"}], tools=[])]
    assert out1 == [Delta(type="token", text="你")] and out2 == [Delta(type="done")]
    assert p.calls[0]["messages"][0]["content"] == "hi"


SSE_BODY = (
    'data: {"choices":[{"delta":{"content":"你"}}]}\n\n'
    'data: {"choices":[{"delta":{"tool_calls":[{"function":{"name":"search_routes","arguments":"{}"}}]}}]}\n\n'
    "data: [DONE]"
)


async def test_openai_compat_parses_sse():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(200, text=SSE_BODY, headers={"Content-Type": "text/event-stream"})

    p = OpenAICompatProvider(base_url="https://8.8.8.8/v1", api_key="k", model="m",
                             transport=httpx.MockTransport(handler))
    deltas = [d async for d in p.chat_stream([{"role": "user", "content": "hi"}], tools=[])]
    assert deltas[0] == Delta(type="token", text="你")
    assert deltas[1].type == "tool_calls"
    assert deltas[1].tool_calls[0]["name"] == "search_routes"


def _shard(delta: dict) -> str:
    return "data: " + json.dumps({"choices": [{"delta": delta}]}, ensure_ascii=False)


# 真实 OpenAI 流按 index 分片：首片带 function.name（arguments 为空），
# 后续片仅携带 arguments 片段，最后 [DONE]。
SHARDED_SSE_BODY = "\n\n".join([
    _shard({"tool_calls": [{"index": 0, "function": {"name": "search_routes", "arguments": ""}}]}),
    _shard({"tool_calls": [{"index": 0, "function": {"arguments": "{\"sport\""}}]}),
    _shard({"tool_calls": [{"index": 0, "function": {"arguments": ":\"hiking\"}"}}]}),
    "data: [DONE]",
]) + "\n\n"


async def test_openai_compat_accumulates_sharded_tool_calls():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=SHARDED_SSE_BODY, headers={"Content-Type": "text/event-stream"})

    p = OpenAICompatProvider(base_url="https://8.8.8.8/v1", api_key="k", model="m",
                             transport=httpx.MockTransport(handler))
    deltas = [d async for d in p.chat_stream([{"role": "user", "content": "hi"}], tools=[])]
    tool_deltas = [d for d in deltas if d.type == "tool_calls"]
    assert len(tool_deltas) == 1
    # 结构断言适配（Task 1 预授权）：产出项新增 id 键，分片流无 wire id → None；
    # 语义断言（name/arguments 累积结果）保持不变。
    call = tool_deltas[0].tool_calls[0]
    assert call["name"] == "search_routes"
    assert call["arguments"] == '{"sport":"hiking"}'
    assert call["id"] is None
    assert deltas[-1].type == "done"


# wire 透传：真实 OpenAI chunk 的 tool_calls 携带原生 id（assistant 声明与 tool
# 消息回传对应的关键），Provider 层必须原样透传给编排层。
WIRE_ID_SSE_BODY = (
    'data: {"choices":[{"delta":{"content":"查"}}]}\n\n'
    'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_x",'
    '"function":{"name":"search_routes","arguments":"{}"}}]}}]}\n\n'
    "data: [DONE]"
)


async def test_openai_compat_passes_through_wire_tool_call_id():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=WIRE_ID_SSE_BODY, headers={"Content-Type": "text/event-stream"})

    p = OpenAICompatProvider(base_url="https://8.8.8.8/v1", api_key="k", model="m",
                             transport=httpx.MockTransport(handler))
    deltas = [d async for d in p.chat_stream([{"role": "user", "content": "hi"}], tools=[])]
    tool_deltas = [d for d in deltas if d.type == "tool_calls"]
    assert len(tool_deltas) == 1
    assert tool_deltas[0].tool_calls == [
        {"id": "call_x", "name": "search_routes", "arguments": "{}"}
    ]
    assert deltas[-1].type == "done"
