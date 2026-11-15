"""quota_tiers/llm_usage/sub_tokens 三表 + users.quota_tier 列（M5-admin Task 2：配额数据层）"""

revision = "0013"
down_revision = "0012"

import sqlalchemy as sa

from alembic import op


def upgrade() -> None:
    op.create_table(
        "quota_tiers",
        # String 主键（非自增）：档位编码即主键（trial/vip）
        sa.Column("tier", sa.String(16), primary_key=True),
        sa.Column("daily_chats", sa.Integer(), nullable=False),
        sa.Column("daily_tokens", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(64)),
    )
    op.create_table(
        "llm_usage",
        # Integer（非 BigInteger）：sqlite 下与 users.id 保持同型（见 0010 trip_plans 先例）
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  index=True, nullable=False),
        sa.Column("session_id", sa.String(32), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "sub_tokens",
        # 纯结构预留（M5 开放平台），无端点
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  index=True, nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("tier", sa.String(16), nullable=False),
        # sa.false()：SQLite 渲染 0 / PG 渲染 false（先例 0012 is_admin/disabled）
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # server_default "trial"：存量用户无需回填，新用户由 ORM default 再兜一层
    op.add_column("users", sa.Column("quota_tier", sa.String(16), nullable=False, server_default="trial"))


def downgrade() -> None:
    op.drop_column("users", "quota_tier")
    op.drop_table("sub_tokens")
    op.drop_table("llm_usage")
    op.drop_table("quota_tiers")
