"""users 增加 is_admin/disabled 标记（M5-admin Task 1：admin 身份与禁用拦截）"""

revision = "0012"
down_revision = "0011"

import sqlalchemy as sa

from alembic import op


def upgrade() -> None:
    # sa.false()：SQLite 渲染 0 / PG 渲染 false（先例 0011 processed；字面 "0" 在 PG 上不可隐式 cast）
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("users", "disabled")
    op.drop_column("users", "is_admin")
