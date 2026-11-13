"""gear_models + user_gear"""

revision = "0003"
down_revision = "0002"

import sqlalchemy as sa

from alembic import op


def upgrade() -> None:
    op.create_table(
        "gear_models",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("item_key", sa.String(32), nullable=False, index=True),
        sa.Column("brand", sa.String(48), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("spec", sa.String(128)),
        sa.UniqueConstraint("item_key", "brand", "model"),
    )
    op.create_table(
        "user_gear",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("item_key", sa.String(32), nullable=False),
        sa.Column("model_id", sa.Integer(), sa.ForeignKey("gear_models.id")),
        sa.Column("custom_name", sa.String(48)),
        sa.Column("acquired_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "item_key", "model_id"),
    )


def downgrade() -> None:
    op.drop_table("user_gear")
    op.drop_table("gear_models")
