"""助手 SSE 端点：POST /assistant/chat（流式事件）、GET /assistant/sessions。"""
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.models.assistant import AssistantSession
from app.models.user import User
from app.services import assistant_service, session_service
from app.services.llm import Provider, get_provider

router = APIRouter()


class ChatIn(BaseModel):
    session_id: str | None = None
    message: str = Field(min_length=1, max_length=2000)


def assistant_provider() -> Provider:
    """生产取配置 Provider；测试经 app.dependency_overrides 注入 FakeProvider。"""
    return get_provider()


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _own_session(db: AsyncSession, user: User, session_id: str) -> AssistantSession:
    sess = (await db.execute(
        select(AssistantSession)
        .where(AssistantSession.id == session_id, AssistantSession.user_id == user.id)
    )).scalar_one_or_none()
    if sess is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return sess


@router.post("/chat")
async def chat(body: ChatIn, user: User = Depends(get_current_user),
               session: AsyncSession = Depends(get_session),
               provider: Provider = Depends(assistant_provider)) -> StreamingResponse:
    existing = None if body.session_id is None else await _own_session(session, user, body.session_id)

    async def gen() -> AsyncIterator[str]:
        if existing is None:
            sess = await session_service.create_session(session, user.id,
                                                        title=body.message[:32])
            yield _sse({"type": "session", "data": sess.id})
        else:
            sess = existing
        async for event in assistant_service.run_chat(session, user, sess, body.message, provider):
            yield _sse(event)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/sessions")
async def list_sessions(user: User = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (await session.execute(
        select(AssistantSession)
        .where(AssistantSession.user_id == user.id)
        .order_by(AssistantSession.created_at.desc(), AssistantSession.id.desc())
    )).scalars().all()
    return [{"id": s.id, "title": s.title, "created_at": s.created_at.isoformat()} for s in rows]
