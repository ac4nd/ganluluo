"""LLM Provider 抽象：Fake（离线测试）与 OpenAI 兼容（httpx 异步流式）。

Delta 事件：token（正文增量）/ tool_calls（工具调用请求）/ done。
工具调用格式：[{id: str | None, name: str, arguments: str}]，arguments 为 JSON 字符串；
id 为 wire 原生 tool_call id 的透传（分片流无 id 时为 None，由编排层合成）。
"""
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
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
    def chat_stream(self, messages: list[dict], tools: list[ToolSpec]) -> AsyncIterator[Delta]: ...


class FakeProvider:
    """脚本化 Provider：每次调用消耗一轮 Delta 序列（测试与离线开发）。"""

    def __init__(self, turns: list[list[Delta]]):
        self.turns = list(turns)
        self.calls: list[dict] = []
        self._idx = 0

    async def chat_stream(self, messages: list[dict], tools: list[ToolSpec]) -> AsyncIterator[Delta]:
        self.calls.append({"messages": [dict(m) for m in messages],
                           "tools": [t.name for t in tools]})
        turn = self.turns[min(self._idx, len(self.turns) - 1)]
        self._idx += 1
        for delta in turn:
            yield delta


class OpenAICompatProvider:
    def __init__(self, base_url: str, api_key: str, model: str,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._transport = transport

    async def chat_stream(self, messages: list[dict], tools: list[ToolSpec]) -> AsyncIterator[Delta]:
        assert_safe_external_url(f"{self.base_url}/chat/completions")
        payload: dict = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = [{"type": "function", "function": {
                "name": t.name, "description": t.description, "parameters": t.parameters}}
                for t in tools]
        async with (httpx.AsyncClient(transport=self._transport, timeout=60) as client,
                    client.stream("POST", f"{self.base_url}/chat/completions",
                                  headers={"Authorization": f"Bearer {self.api_key}"},
                                  json=payload) as resp):
            resp.raise_for_status()
            # 真实 OpenAI 流按 index 分片下发 tool_calls：首片含 function.name（及 id）
            # （arguments 常为空串），续片仅携带 arguments 片段。逐片累积，
            # 流结束（[DONE] 或对端关闭）时一次性吐出完整的 tool_calls Delta。
            # id 为 wire 原生 tool_call id：同组取首片携带的 id（无则 None）。
            pending: dict[int, tuple[str | None, str | None, list[str]]] = {}
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[len("data: "):]
                if data.strip() == "[DONE]":
                    break
                chunk = json.loads(data)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                if delta.get("content"):
                    yield Delta(type="token", text=delta["content"])
                for tc in delta.get("tool_calls") or []:
                    fn = tc.get("function")
                    if not fn:
                        continue
                    idx = int(tc.get("index", 0))
                    name, call_id, parts = pending.get(idx, (None, None, []))
                    if call_id is None and tc.get("id"):
                        call_id = tc["id"]
                    if fn.get("name"):
                        name = fn["name"]
                    if fn.get("arguments"):
                        parts.append(fn["arguments"])
                    pending[idx] = (name, call_id, parts)
            if pending:
                calls = [{"id": pending[i][1],
                          "name": pending[i][0] or "",
                          "arguments": "".join(pending[i][2]) or "{}"}
                         for i in sorted(pending)]
                yield Delta(type="tool_calls", tool_calls=calls)
        yield Delta(type="done")


def get_provider() -> Provider:
    from app.core.config import get_settings
    s = get_settings()
    if s.llm_base_url and s.llm_api_key:
        return OpenAICompatProvider(s.llm_base_url, s.llm_api_key, s.llm_model)
    return FakeProvider(turns=[[Delta(type="token", text="(离线模式：未配置 LLM)"),
                               Delta(type="done")]])
