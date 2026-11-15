"""agent_sessions/messages → assistant_sessions/messages（AI 层命名还原为 assistant）"""

revision = "0008"
down_revision = "0007"

from alembic import op


def upgrade() -> None:
    # PG 上 rename_table 会连带更新 FK 指向；索引名需显式对齐
    op.rename_table("agent_sessions", "assistant_sessions")
    op.rename_table("agent_messages", "assistant_messages")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER INDEX ix_agent_sessions_user_id RENAME TO ix_assistant_sessions_user_id")
        op.execute("ALTER INDEX ix_agent_messages_session_id RENAME TO ix_assistant_messages_session_id")


def downgrade() -> None:
    op.rename_table("assistant_sessions", "agent_sessions")
    op.rename_table("assistant_messages", "agent_messages")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER INDEX ix_assistant_sessions_user_id RENAME TO ix_agent_sessions_user_id")
        op.execute("ALTER INDEX ix_assistant_messages_session_id RENAME TO ix_agent_messages_session_id")
