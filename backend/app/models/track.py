from sqlalchemy import ForeignKey, String, false
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RouteTrack(Base):
    __tablename__ = "route_tracks"

    # Plain Integer PKs (project pattern, see User/migration 0001): BigInteger
    # PKs do not autoincrement on SQLite (rowid aliasing needs INTEGER PRIMARY KEY).
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id", ondelete="CASCADE"), index=True)
    # DDL §5.2 原样四业务字段（无 created_at）：gpx_object 存相对 key "tracks/{uuid4hex}.gpx"
    gpx_object: Mapped[str] = mapped_column(String(256))
    points: Mapped[int] = mapped_column()
    processed: Mapped[bool] = mapped_column(default=False, server_default=false())
