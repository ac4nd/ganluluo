from datetime import datetime

from sqlalchemy import DateTime, String, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True)
    nickname: Mapped[str] = mapped_column(String(32))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    oauth_provider: Mapped[str | None] = mapped_column(String(16))
    oauth_subject: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # M5-admin Task 1：管理端身份与禁用标记
    # false()：SQLite 渲染 0 / PG 渲染 false（先例 track.processed；字面 "0" 在 PG 上不可隐式 cast）
    is_admin: Mapped[bool] = mapped_column(default=False, server_default=false())
    disabled: Mapped[bool] = mapped_column(default=False, server_default=false())
    # M5-admin Task 2：配额档位（trial/vip）；server_default 兜住存量行与迁移列
    quota_tier: Mapped[str] = mapped_column(String(16), default="trial", server_default="trial")
