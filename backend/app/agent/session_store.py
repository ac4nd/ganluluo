import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentMessage, AgentSession


async def create_session(session: AsyncSession, user_id: int, title: str = "") -> AgentSession:
    sess = AgentSession(id=uuid.uuid4().hex, user_id=user_id, title=title)
    session.add(sess)
    await session.commit()
    return sess


async def own_session(session: AsyncSession, user_id: int,
                      session_id: str) -> AgentSession | None:
    """按 id 查本人会话；不存在或非本人返回 None。"""
    stmt = select(AgentSession).where(
        AgentSession.id == session_id, AgentSession.user_id == user_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_sessions(session: AsyncSession, user_id: int) -> list[AgentSession]:
    """用户的会话列表，按创建时间倒序（新会话在前）。"""
    stmt = (select(AgentSession)
            .where(AgentSession.user_id == user_id)
            .order_by(AgentSession.created_at.desc(), AgentSession.id.desc()))
    return list((await session.execute(stmt)).scalars().all())


async def append_message(session: AsyncSession, sess: AgentSession, role: str,
                         content: str, tool_name: str | None = None) -> AgentMessage:
    msg = AgentMessage(session_id=sess.id, role=role, content=content, tool_name=tool_name)
    session.add(msg)
    await session.commit()
    return msg


async def recent_messages(session: AsyncSession, session_id: str, limit: int = 20) -> list[AgentMessage]:
    stmt = (select(AgentMessage)
            .where(AgentMessage.session_id == session_id,
                   AgentMessage.role.in_(("user", "assistant")))
            .order_by(AgentMessage.id.desc()).limit(limit))
    rows = list((await session.execute(stmt)).scalars().all())
    rows.reverse()
    return rows


async def save_summary(session: AsyncSession, session_id: str, summary: str) -> None:
    sess = (await session.execute(select(AgentSession).where(AgentSession.id == session_id))).scalar_one()
    sess.summary = summary
    await session.commit()


async def set_clarify(session: AsyncSession, session_id: str, state: dict | None) -> None:
    sess = (await session.execute(select(AgentSession).where(AgentSession.id == session_id))).scalar_one()
    sess.clarify = state
    await session.commit()
