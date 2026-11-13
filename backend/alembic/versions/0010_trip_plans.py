"""trip_plans（行程计划单表：路线 × 日期 × 集合点，M4-trip Task 1）"""

revision = "0010"
down_revision = "0008"

import sqlalchemy as sa

from alembic import op


def upgrade() -> None:
    op.create_table(
        "trip_plans",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        # Integer（非 BigInteger）：sqlite 下与 users.id 保持同型（见 0003 user_gear 先例）
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  index=True, nullable=False),
        # 无 ON DELETE（DDL §5.2 原样）：路线删除由 routes 侧管理，默认 RESTRICT
        sa.Column("route_id", sa.Integer(), sa.ForeignKey("routes.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("meet_at", sa.Time(), nullable=False),
        sa.Column("meet_place", sa.String(96)),
        sa.Column("status", sa.String(16), nullable=False, server_default="planned"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("trip_plans")
