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
