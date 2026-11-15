"""记忆抽取结果结构（UserMemory 落库前的轻量载体）。"""
from typing import Literal

from pydantic import BaseModel

MemoryKind = Literal["preference", "constraint", "fact"]


class MemoryFact(BaseModel):
    kind: MemoryKind
    content: str
    confidence: float = 0.8
    source_session: str | None = None
