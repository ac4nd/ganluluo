"""media_items 表（M6-media Task 1：媒体数据层，presigned upload + 审核状态机）"""

revision = "0014"
down_revision = "0013"

import sqlalchemy as sa

from alembic import op


def upgrade() -> None:
    op.create_table(
        "media_items",
        # Integer（非 BigInteger）：sqlite 下与 users.id 保持同型（见 0010 trip_plans 先例）
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  index=True, nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("object_key", sa.String(256), nullable=False, unique=True),
        # server_default "pending"：审核状态机起点（pending → approved/rejected，Task 3）
        sa.Column("status", sa.String(8), nullable=False, server_default="pending"),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("mime", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("media_items")
