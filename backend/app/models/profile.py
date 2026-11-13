from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

JsonVariant = JSON().with_variant(JSONB(), "postgresql")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    sports: Mapped[list] = mapped_column(JsonVariant, default=list)
    exp_level: Mapped[int] = mapped_column(default=1)
    fitness: Mapped[int] = mapped_column(default=2)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
