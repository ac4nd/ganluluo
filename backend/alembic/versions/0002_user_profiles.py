"""user_profiles"""

revision = "0002"
down_revision = "0001"

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("sports", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("exp_level", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
        sa.Column("fitness", sa.SmallInteger(), nullable=False, server_default=sa.text("2")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_profiles")
