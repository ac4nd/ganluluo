"""长期记忆：启发式抽取 → MemoryFact；UserMemory 落库与按用户查询。"""
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assistant import UserMemory
from app.domains.assistant.memory_schemas import MemoryFact, MemoryKind

# 触发词按序匹配；"我不喜欢" 不含 "我喜欢" 子串，与 preference 无冲突
_PREFERENCE_TRIGGERS = ("我喜欢", "我爱", "偏好")
_CONSTRAINT_TRIGGERS = ("我怕", "我不喜欢", "不想要")
_FACT_PATTERNS = (re.compile(r"我的.+是"), re.compile(r"我有.+年.+经验"))

_SENTENCE_SPLIT = re.compile(r"[。？！!?;\n]")


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def classify_sentence(sentence: str) -> MemoryKind | None:
    """单句启发式分类：无触发词返回 None。"""
    if any(t in sentence for t in _PREFERENCE_TRIGGERS):
        return "preference"
    if any(t in sentence for t in _CONSTRAINT_TRIGGERS):
        return "constraint"
    if any(p.search(sentence) for p in _FACT_PATTERNS):
        return "fact"
    return None


def extract_memories(messages: list[str]) -> list[MemoryFact]:
    """从消息文本中抽取记忆：命中触发词的句子（可能一句一条），confidence 0.8。"""
    facts: list[MemoryFact] = []
    for message in messages:
        for sentence in _split_sentences(message):
            kind = classify_sentence(sentence)
            if kind is not None:
                facts.append(MemoryFact(kind=kind, content=sentence))
    return facts


async def save_memories(session: AsyncSession, user_id: int, facts: list[MemoryFact],
                        source_session: str | None = None) -> int:
    """批量落库（source_session 优先取入参，回退 fact 自带值），返回写入条数。"""
    for f in facts:
        session.add(UserMemory(user_id=user_id, kind=f.kind, content=f.content,
                               confidence=f.confidence,
                               source_session=source_session or f.source_session))
    await session.commit()
    return len(facts)


async def list_memories(session: AsyncSession, user_id: int) -> list[UserMemory]:
    stmt = (select(UserMemory)
            .where(UserMemory.user_id == user_id)
            .order_by(UserMemory.created_at.desc(), UserMemory.id.desc()))
    return list((await session.execute(stmt)).scalars().all())


async def delete_memory(session: AsyncSession, user_id: int, memory_id: int) -> bool:
    """删除本人记忆；不存在或非本人返回 False，删除成功返回 True。"""
    stmt = select(UserMemory).where(UserMemory.id == memory_id, UserMemory.user_id == user_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.commit()
    return True
