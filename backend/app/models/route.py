from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

JsonVariant = JSON().with_variant(JSONB(), "postgresql")


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))
    region: Mapped[str] = mapped_column(String(64))
    sport: Mapped[str] = mapped_column(String(16))
    difficulty: Mapped[int] = mapped_column(default=1)
    distance_km: Mapped[float] = mapped_column(Float)
    climb_m: Mapped[int] = mapped_column(default=0)
    duration_h: Mapped[float | None] = mapped_column(Float, nullable=True)
    clarity: Mapped[str] = mapped_column(String(8), default="mid")
    terrain: Mapped[list] = mapped_column(JsonVariant, default=list)
    elevation: Mapped[list] = mapped_column(JsonVariant, default=list)
    pace: Mapped[list] = mapped_column(JsonVariant, default=list)
    required_gear: Mapped[list] = mapped_column(JsonVariant, default=list)
    warning: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    track_points: Mapped[list | None] = mapped_column(JsonVariant, nullable=True)
    # M8.8：封面图完整访问 URL（MinIO 公共读 covers/{id}.jpg）；NULL → 前端渐变模板回退
    cover_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source: Mapped[str] = mapped_column(String(16), default="seed")
    status: Mapped[str] = mapped_column(String(16), default="published")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
