from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class QuotaTier(Base):
    __tablename__ = "quota_tiers"

    # String 主键（非自增）：档位编码即主键（trial/vip），DDL 原样
    tier: Mapped[str] = mapped_column(String(16), primary_key=True)
    daily_chats: Mapped[int] = mapped_column()
    daily_tokens: Mapped[int] = mapped_column()
    description: Mapped[str | None] = mapped_column(String(64))


class LlmUsage(Base):
    __tablename__ = "llm_usage"

    # Plain Integer PKs (project pattern, see User/migration 0001): BigInteger
    # PKs do not autoincrement on SQLite (rowid aliasing needs INTEGER PRIMARY KEY).
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    prompt_tokens: Mapped[int] = mapped_column()
    completion_tokens: Mapped[int] = mapped_column()
    total_tokens: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SubToken(Base):
    __tablename__ = "sub_tokens"

    # 纯结构预留（M5 开放平台），无端点（M3.5 计划原样）
    # Plain Integer PKs (project pattern, see User/migration 0001): BigInteger
    # PKs do not autoincrement on SQLite (rowid aliasing needs INTEGER PRIMARY KEY).
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64))
    tier: Mapped[str] = mapped_column(String(16))
    # false()：SQLite 渲染 0 / PG 渲染 false（先例 track.processed；字面 "0" 在 PG 上不可隐式 cast）
    revoked: Mapped[bool] = mapped_column(default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
