"""routes 表（双方言：postgresql 追加 geography + GIST）"""

revision = "0004"
down_revision = "0003"

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# 与模型 route.py 的 JsonVariant 保持一致：PG 上建 JSONB
JsonVariant = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "routes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("region", sa.String(64), nullable=False),
        sa.Column("sport", sa.String(16), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=False),
        sa.Column("distance_km", sa.Float(), nullable=False),
        sa.Column("climb_m", sa.Integer(), nullable=False),
        sa.Column("duration_h", sa.Float()),
        sa.Column("clarity", sa.String(8), nullable=False),
        sa.Column("terrain", JsonVariant, nullable=False, server_default="[]"),
        sa.Column("elevation", JsonVariant, nullable=False, server_default="[]"),
        sa.Column("pace", JsonVariant, nullable=False, server_default="[]"),
        sa.Column("required_gear", JsonVariant, nullable=False, server_default="[]"),
        sa.Column("warning", sa.String(255)),
        sa.Column("start_lat", sa.Float()),
        sa.Column("start_lon", sa.Float()),
        sa.Column("track_points", JsonVariant),
        sa.Column("source", sa.String(16), nullable=False, server_default="seed"),
        sa.Column("status", sa.String(16), nullable=False, server_default="published"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_routes_region", "routes", ["region"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
        op.execute("ALTER TABLE routes ADD COLUMN start_pt geography(Point,4326)")
        op.execute("UPDATE routes SET start_pt = ST_SetSRID(ST_MakePoint(start_lon, start_lat), 4326)::geography")
        op.execute("CREATE INDEX idx_routes_start_pt ON routes USING GIST (start_pt)")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.drop_index("idx_routes_start_pt", table_name="routes")
    op.drop_table("routes")
