"""kb_docs + kb_chunks（双方言：PG 分支 embedding 列转 vector(1024) + HNSW 索引）"""

revision = "0006"
down_revision = "0005"

import sqlalchemy as sa

from alembic import op

# 与模型 kb.py 的 EmbeddingVariant 保持一致：先建 JSON，PG 分支再转 vector(1024)


def upgrade() -> None:
    op.create_table(
        "kb_docs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_name", sa.String(128), nullable=False),
        sa.Column("sport", sa.String(16)),
        sa.Column("doc_type", sa.String(16), nullable=False, server_default="guide"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("uq_kb_docs_source_name", "kb_docs", ["source_name"], unique=True)
    op.create_table(
        "kb_chunks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("doc_id", sa.Integer(), sa.ForeignKey("kb_docs.id", ondelete="CASCADE"),
                  index=True, nullable=False),
        sa.Column("chunk_no", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sport", sa.String(16)),
        sa.Column("region", sa.String(64)),
        sa.Column("section", sa.String(128)),
        sa.Column("tokens", sa.Integer(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=False),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute("ALTER TABLE kb_chunks ALTER COLUMN embedding TYPE vector(1024) USING NULL")
        op.execute("CREATE INDEX idx_chunks_hnsw ON kb_chunks USING hnsw (embedding vector_cosine_ops)")


def downgrade() -> None:
    op.drop_table("kb_chunks")
    op.drop_index("uq_kb_docs_source_name", table_name="kb_docs")
    op.drop_table("kb_docs")
