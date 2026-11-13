from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GearModel(Base):
    __tablename__ = "gear_models"
    __table_args__ = (UniqueConstraint("item_key", "brand", "model"),)

    # Plain Integer PKs (project pattern, see User/migration 0001): BigInteger
    # PKs do not autoincrement on SQLite (rowid aliasing needs INTEGER PRIMARY KEY).
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_key: Mapped[str] = mapped_column(String(32), index=True)
    brand: Mapped[str] = mapped_column(String(48))
    model: Mapped[str] = mapped_column(String(64))
    spec: Mapped[str | None] = mapped_column(String(128))


class UserGear(Base):
    __tablename__ = "user_gear"
    __table_args__ = (UniqueConstraint("user_id", "item_key", "model_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    item_key: Mapped[str] = mapped_column(String(32))
    model_id: Mapped[int | None] = mapped_column(ForeignKey("gear_models.id"))
    custom_name: Mapped[str | None] = mapped_column(String(48))
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
