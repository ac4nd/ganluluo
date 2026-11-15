from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# sqlite/json 落 JSON 数组；postgresql 落 vector(1024)（迁移 0006 PG 分支转换）
EmbeddingVariant = JSON().with_variant(Vector(1024), "postgresql")


class KbDoc(Base):
    __tablename__ = "kb_docs"
    __table_args__ = (
        Index("uq_kb_docs_source_name", "source_name", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_name: Mapped[str] = mapped_column(String(128))
    sport: Mapped[str | None] = mapped_column(String(16), nullable=True)
    doc_type: Mapped[str] = mapped_column(String(16), default="guide")
    version: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(16), default="indexed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KbChunk(Base):
    __tablename__ = "kb_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(
        ForeignKey("kb_docs.id", ondelete="CASCADE"), index=True
    )
    chunk_no: Mapped[int]
    content: Mapped[str] = mapped_column(Text)
    sport: Mapped[str | None] = mapped_column(String(16), nullable=True)
    region: Mapped[str | None] = mapped_column(String(64), nullable=True)
    section: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tokens: Mapped[int]
    embedding: Mapped[list] = mapped_column(EmbeddingVariant)
