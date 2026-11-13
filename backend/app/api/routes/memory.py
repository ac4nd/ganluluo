"""记忆 API：GET /assistant/memory 列表、DELETE /assistant/memory/{id}（归属校验）。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.models.assistant import UserMemory
from app.models.user import User
from app.services import memory_service

router = APIRouter(prefix="/memory")


@router.get("")
async def list_memory(user: User = Depends(get_current_user),
                      session: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = await memory_service.list_memories(session, user.id)
    return [{"id": r.id, "kind": r.kind, "content": r.content,
             "confidence": r.confidence, "created_at": r.created_at.isoformat()} for r in rows]


@router.delete("/{memory_id}")
async def delete_memory(memory_id: int, user: User = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)) -> dict:
    row = (await session.execute(
        select(UserMemory)
        .where(UserMemory.id == memory_id, UserMemory.user_id == user.id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    await session.delete(row)
    await session.commit()
    return {"ok": True}
