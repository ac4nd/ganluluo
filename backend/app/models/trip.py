from datetime import date, datetime, time

from sqlalchemy import Date, DateTime, ForeignKey, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TripPlan(Base):
    __tablename__ = "trip_plans"

    # Plain Integer PKs (project pattern, see User/migration 0001): BigInteger
    # PKs do not autoincrement on SQLite (rowid aliasing needs INTEGER PRIMARY KEY).
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # DDL §5.2 原样：route_id 无 ON DELETE——路线删除由 routes 侧管理（默认 RESTRICT）
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"))
    date: Mapped[date] = mapped_column(Date)
    meet_at: Mapped[time] = mapped_column(Time)
    meet_place: Mapped[str | None] = mapped_column(String(96))
    status: Mapped[str] = mapped_column(String(16), default="planned", server_default="planned")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
