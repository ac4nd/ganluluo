"""route_tracks（轨迹上传表：路线 × GPX 对象 + 处理状态，M4.5-tracks Task 1）"""

revision = "0011"
down_revision = "0010"

import sqlalchemy as sa

from alembic import op


def upgrade() -> None:
    op.create_table(
        "route_tracks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        # Integer（非 BigInteger）：sqlite 下与 users.id 保持同型（见 0003 user_gear 先例）
        sa.Column("route_id", sa.Integer(), sa.ForeignKey("routes.id", ondelete="CASCADE"),
                  index=True, nullable=False),
        sa.Column("gpx_object", sa.String(256), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        # sa.false()：SQLite 渲染 0 / PG 渲染 false（先例 0001 revoked；字面 "0" 在 PG 上不可隐式 cast）
        sa.Column("processed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_table("route_tracks")
