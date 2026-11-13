# tests/test_llm.py
import httpx

from app.services.llm import Delta, FakeProvider, OpenAICompatProvider


def test_fake_provider_turns():
    p = FakeProvider(turns=[[Delta(type="token", text="你")],
                            [Delta(type="done")]])
    out1 = list(p.chat_stream([{"role": "user", "content": "hi"}], tools=[]))
    out2 = list(p.chat_stream([{"role": "user", "content": "hi"}], tools=[]))
    assert out1 == [Delta(type="token", text="你")] and out2 == [Delta(type="done")]
    assert p.calls[0]["messages"][0]["content"] == "hi"


SSE_BODY = (
    'data: {"choices":[{"delta":{"content":"你"}}]}\n\n'
    'data: {"choices":[{"delta":{"tool_calls":[{"function":{"name":"search_routes","arguments":"{}"}}]}}]}\n\n'
    "data: [DONE]"
)


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
