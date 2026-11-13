from app.services.session_service import (
    append_message,
    create_session,
    recent_messages,
    save_summary,
    set_clarify,
)


async def test_session_roundtrip(db):
    sess = await create_session(db, user_id=1, title="周末去哪")
    assert len(sess.id) == 32  # uuid hex
    for i in range(25):
        await append_message(db, sess, "user" if i % 2 == 0 else "assistant", f"m{i}")
    # role 过滤：tool 消息不进入 recent_messages（26 行里 25 行是对话消息）
    await append_message(db, sess, "tool", "route_search ok", tool_name="route_search")
    recent = await recent_messages(db, sess.id, limit=20)
    assert len(recent) == 20 and recent[-1].content == "m24" and recent[0].content == "m5"
    await save_summary(db, sess.id, "讨论了徽杭古道")
    await set_clarify(db, sess.id, {"intent": "plan", "slots": {"sport": "hiking"}, "asked": [], "round_no": 1})
    sid = sess.id
    db.expire_all()
    # 校准断言：上面写入的对话消息 role 全部是 user/assistant，因此 recent_messages(limit=1)
    # 的真实返回是最新一条（m24，role=user），brief 原始的 `fresh == []` 不成立。
    # 断言保留原意：expire_all 之后查询不炸（行属性由本次 SELECT 直接填充）。
    fresh = await recent_messages(db, sid, limit=1)
    assert len(fresh) == 1 and fresh[0].role == "user" and fresh[0].content == "m24"
    # save_summary / set_clarify 确实落库：refresh 强制从 DB 重读
    await db.refresh(sess)
    assert sess.summary == "讨论了徽杭古道"
    assert sess.clarify == {"intent": "plan", "slots": {"sport": "hiking"}, "asked": [], "round_no": 1}
