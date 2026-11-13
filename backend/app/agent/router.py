"""agent SSE 端点：POST /agent/chat（流式事件）、GET /agent/sessions。"""
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import orchestrator as agent_service
from app.agent import session_store as session_service
from app.agent.llm import Provider, get_provider
from app.api.deps import get_current_user
from app.core.db import get_session
from app.models.user import User

router = APIRouter()


class ChatIn(BaseModel):
    session_id: str | None = None
    message: str = Field(min_length=1, max_length=2000)


def agent_provider() -> Provider:
    """生产取配置 Provider；测试经 app.dependency_overrides 注入 FakeProvider。"""
    return get_provider()


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/chat")
async def chat(body: ChatIn, user: User = Depends(get_current_user),
               session: AsyncSession = Depends(get_session),
               provider: Provider = Depends(agent_provider)) -> StreamingResponse:
    existing = None
    if body.session_id is not None:
        existing = await session_service.own_session(session, user.id, body.session_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="会话不存在")

    async def gen() -> AsyncIterator[str]:
        if existing is None:
            sess = await session_service.create_session(session, user.id,
                                                        title=body.message[:32])
            yield _sse({"type": "session", "data": sess.id})
        else:
            sess = existing
        async for event in agent_service.run_chat(session, user, sess, body.message, provider):
            yield _sse(event)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/sessions")
async def list_sessions(user: User = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = await session_service.list_sessions(session, user.id)
    return [{"id": s.id, "title": s.title, "created_at": s.created_at.isoformat()} for s in rows]
