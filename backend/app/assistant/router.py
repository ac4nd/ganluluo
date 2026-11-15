"""助手 SSE 端点：POST /assistant/chat（流式事件）、GET /assistant/sessions 与 /quota。"""
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.assistant import orchestrator as assistant_service
from app.assistant import session_store as session_service
from app.assistant.llm import Provider, get_provider
from app.core.db import get_session
from app.core.rate_limit import limiter, user_key
from app.domains.admin.quota_service import get_status
from app.domains.admin.schemas import UsageOut
from app.models.user import User

router = APIRouter()


class ChatIn(BaseModel):
    session_id: str | None = None
    message: str = Field(min_length=1, max_length=2000)


def assistant_provider() -> Provider:
    """生产取配置 Provider；测试经 app.dependency_overrides 注入 FakeProvider。"""
    return get_provider()


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/chat")
# 短窗防刷（5/minute per-user），与日配额（5/day）相互独立：slowapi 在端点执行前
# 检查，超限抛 RateLimitExceeded → main.py handler 返回 JSON 429（SSE 未开始）。
# user_key（M6.5 I-6）已抽到 core/rate_limit.py 共享，媒体登记限流同款键。
@limiter.limit("5/minute", key_func=user_key)
async def chat(request: Request, body: ChatIn, user: User = Depends(get_current_user),
               session: AsyncSession = Depends(get_session),
               provider: Provider = Depends(assistant_provider)) -> StreamingResponse:
    existing = None
    if body.session_id is not None:
        existing = await session_service.own_session(session, user.id, body.session_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="会话不存在")

    # 日配额状态读取一次传入 run_chat（闸门在其内部、消息落库之前）
    quota = await get_status(session, user.id, user.quota_tier)

    async def gen() -> AsyncIterator[str]:
        if existing is None:
            sess = await session_service.create_session(session, user.id,
                                                        title=body.message[:32])
            yield _sse({"type": "session", "data": sess.id})
        else:
            sess = existing
        async for event in assistant_service.run_chat(session, user, sess, body.message,
                                                      provider, quota=quota):
            yield _sse(event)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/sessions")
async def list_sessions(user: User = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = await session_service.list_sessions(session, user.id)
    return [{"id": s.id, "title": s.title, "created_at": s.created_at.isoformat()} for s in rows]


@router.get("/quota", response_model=UsageOut)
async def my_quota(user: User = Depends(get_current_user),
                   session: AsyncSession = Depends(get_session)) -> UsageOut:
    """用户侧当日配额（06 环形按钮 / 09 额度卡数据源）。"""
    st = await get_status(session, user.id, user.quota_tier)
    return UsageOut(chats_used=st.daily_chats_used, tokens_used=st.daily_tokens_used,
                    tier=user.quota_tier, daily_chats_limit=st.daily_chats_limit,
                    daily_tokens_limit=st.daily_tokens_limit, allowed=st.allowed)
