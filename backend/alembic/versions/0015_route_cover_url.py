"""routes.cover_url 列（M8.8-covers-minio：路线封面图 MinIO 公共读 URL）"""

revision = "0015"
down_revision = "0014"

import sqlalchemy as sa

from alembic import op


def upgrade() -> None:
    # 完整访问 URL（http://{endpoint}/{bucket}/covers/{id}.jpg）；未上传封面为 NULL，
    # 前端按 cover_url 非空与否决定真实封面或渐变模板回退
    op.add_column("routes", sa.Column("cover_url", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("routes", "cover_url")
