from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MediaItem(Base):
    __tablename__ = "media_items"

    # Plain Integer PKs (project pattern, see User/migration 0001): BigInteger
    # PKs do not autoincrement on SQLite (rowid aliasing needs INTEGER PRIMARY KEY).
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # MVP 仅 'video' 常量；审核扩展再添 'image' 等
    kind: Mapped[str] = mapped_column(String(8), default="video")
    object_key: Mapped[str] = mapped_column(String(256), unique=True)
    # 审核状态机：pending → approved / rejected（Task 3 admin 审核）
    status: Mapped[str] = mapped_column(String(8), default="pending", server_default="pending")
    size_bytes: Mapped[int] = mapped_column()
    mime: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
