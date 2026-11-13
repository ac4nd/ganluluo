"""assistant_sessions + assistant_messages + user_memories"""

revision = "0005"
down_revision = "0004"

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# 与模型 assistant.py 的 JsonVariant 保持一致：PG 上建 JSONB
JsonVariant = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "assistant_sessions",
        sa.Column("id", sa.String(32), primary_key=True),
        # Integer（非 BigInteger）：sqlite 下与 users.id 保持同型（见 0003 user_gear 先例）
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  index=True, nullable=False),
        sa.Column("title", sa.String(128)),
        sa.Column("summary", sa.Text()),
        sa.Column("clarify", JsonVariant),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "assistant_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(32), sa.ForeignKey("assistant_sessions.id", ondelete="CASCADE"),
                  index=True, nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_name", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "user_memories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  index=True, nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("0.8")),
        sa.Column("source_session", sa.String(32)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('preference', 'constraint', 'fact')", name="ck_user_memories_kind"),
    )


def downgrade() -> None:
    op.drop_table("user_memories")
    op.drop_table("assistant_messages")
    op.drop_table("assistant_sessions")
