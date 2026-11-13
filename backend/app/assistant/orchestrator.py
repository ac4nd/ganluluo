"""对话编排：澄清状态机 → 知识检索 → 工具调用循环 → SSE 事件流。

事件协议：{"type": "token"|"clarify"|"cards"|"sources"|"done", "data": ...}。
"""
import json
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant import knowledge
from app.assistant import session_store as session_service
from app.assistant import tools as tool_registry
from app.assistant.clarify import detect_intent, extract_slots, next_clarification
from app.assistant.clarify_schemas import ClarifyState
from app.assistant.llm import Provider
from app.domains.sports import profile_service
from app.models.assistant import AssistantSession
from app.models.user import User

PERSONA = "你是「甘露罗」户外助手，一位严谨、友善的户外路线顾问。"
MAX_TOOL_ROUNDS = 3
RECENT_LIMIT = 20


async def run_chat(session: AsyncSession, user: User, sess: AssistantSession,
                   message: str, provider: Provider) -> AsyncIterator[dict]:
    """编排一轮对话：落库用户消息 → 澄清判定 → 检索 → 组装上下文 → 流式生成。"""
    await session_service.append_message(session, sess, "user", message)

    state = ClarifyState(**sess.clarify) if sess.clarify else ClarifyState()
    intent = detect_intent(message)
    # 澄清链路进行中（上轮已追问且仍是 plan）时，裸回答（如「徒步」）判为 chat
    # 不应打断追问链：保留 plan 意图继续收槽
    if state.round_no > 0 and state.intent == "plan" and intent == "chat":
        intent = "plan"
    state = extract_slots(message, state).model_copy(update={"intent": intent})

    clarification = next_clarification(state)
    if clarification is not None:
        state = state.model_copy(update={"round_no": state.round_no + 1,
                                         "asked": [*state.asked, str(clarification["slot"])]})
        await session_service.set_clarify(session, sess.id, state.model_dump())
        await session_service.append_message(session, sess, "assistant",
                                             str(clarification["question"]))
        yield {"type": "clarify", "data": clarification}
        yield {"type": "done"}
        return

    # 无需澄清：plan 意图且已收集槽位时保留状态（清掉 skip 瞬态键）供后续轮消费，
    # 其余情况清空
    if intent == "plan" and state.slots:
        state = state.model_copy(
            update={"slots": {k: v for k, v in state.slots.items() if k != "skip"}})
        await session_service.set_clarify(session, sess.id, state.model_dump())
    else:
        await session_service.set_clarify(session, sess.id, None)

    sources = await knowledge.search(session, message,
                                             sport=state.slots.get("sport") or None)
    if sources:
        yield {"type": "sources",
               "data": [{"source_name": s["source_name"], "chunk_no": s["chunk_no"]}
                        for s in sources]}

    profile = await profile_service.get_or_create(session, user.id)
    parts = [PERSONA,
             f"用户画像：运动偏好 {'/'.join(profile.sports) or '未知'}；体能等级 {profile.fitness}。"]
    if sess.summary:
        parts.append(f"会话摘要：{sess.summary}")
    known = {k: v for k, v in state.slots.items() if k != "skip"}
    if known:
        parts.append(f"用户已知偏好: {', '.join(f'{k}={v}' for k, v in known.items())}")
    system = "\n".join(parts)
    messages: list[dict] = [{"role": "system", "content": system}]
    if sources:
        messages.append({"role": "system",
                         "content": f"参考资料:\n{str(sources[0]['content'])[:400]}"})
    # 用户消息已 append，recent（含该条）即完整对话上下文
    recent = await session_service.recent_messages(session, sess.id, RECENT_LIMIT)
    messages.extend({"role": m.role, "content": m.content} for m in recent)

    text_parts: list[str] = []
    for _round in range(MAX_TOOL_ROUNDS):
        round_text: list[str] = []
        calls: list[dict] = []
        for delta in provider.chat_stream(messages, tool_registry.TOOL_SPECS):
            if delta.type == "token" and delta.text:
                round_text.append(delta.text)
                yield {"type": "token", "data": delta.text}
            elif delta.type == "tool_calls" and delta.tool_calls:
                calls.extend(delta.tool_calls)
        text_parts.extend(round_text)
        if not calls:
            break
        messages.append({"role": "assistant", "content": "".join(round_text),
                         "tool_calls": [{"name": str(c.get("name", "")),
                                         "arguments": str(c.get("arguments", "{}"))}
                                        for c in calls]})
        cards: list[dict] = []
        for call_id, call in enumerate(calls):
            name = str(call.get("name", ""))
            try:
                arguments = json.loads(call.get("arguments") or "{}")
                if not isinstance(arguments, dict):
                    arguments = {}
            except json.JSONDecodeError:
                arguments = {}
            try:
                result = await tool_registry.execute_tool(session, user, name, arguments)
            except ValueError as exc:
                result = {"error": str(exc)}
            content = json.dumps(result, ensure_ascii=False)[:2000]
            await session_service.append_message(session, sess, "tool", content,
                                                 tool_name=name)
            if name == "search_routes":
                cards.extend(result.get("cards", []))
            messages.append({"role": "tool", "tool_call_id": str(call_id),
                             "name": name, "content": content})
        if cards:
            yield {"type": "cards", "data": cards}

    await session_service.append_message(session, sess, "assistant", "".join(text_parts))
    yield {"type": "done"}
