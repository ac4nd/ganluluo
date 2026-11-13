"""知识库摄取：按 source_name 幂等重建（内容变化 → 删旧块、版本 +1、重嵌入）。"""
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.chunker import chunk_text
from app.agent.embedder import Embedder, get_embedder
from app.models.kb import KbChunk, KbDoc


async def ingest_document(session: AsyncSession, source_name: str, text: str,
                          sport: str | None = None, region: str | None = None,
                          embedder: Embedder | None = None) -> int:
    """摄取一篇文档：分块 → 嵌入 → 存 doc + chunks，返回本次写入块数。

    幂等：同名且块内容一致 → 直接返回 0（不重建）；
    内容变化 → 删旧 chunks 与 doc 行，version +1 重建。
    """
    chunks = chunk_text(text)

    existing = (await session.execute(
        select(KbDoc).where(KbDoc.source_name == source_name)
    )).scalar_one_or_none()
    if existing is not None:
        old_contents = [row[0] for row in (await session.execute(
            select(KbChunk.content)
            .where(KbChunk.doc_id == existing.id)
            .order_by(KbChunk.chunk_no)
        )).all()]
        if old_contents == chunks:
            return 0
        version = existing.version + 1
        await session.execute(delete(KbChunk).where(KbChunk.doc_id == existing.id))
        await session.execute(delete(KbDoc).where(KbDoc.id == existing.id))
    else:
        version = 1

    doc = KbDoc(source_name=source_name, sport=sport, doc_type="guide",
                version=version, status="indexed")
    session.add(doc)
    await session.flush()  # 取 doc.id

    vectors = (embedder or get_embedder()).embed(chunks)
    first_line = next((line.strip() for line in text.split("\n") if line.strip()), "")
    for no, (content, vector) in enumerate(zip(chunks, vectors)):
        session.add(KbChunk(doc_id=doc.id, chunk_no=no, content=content,
                            sport=sport, region=region,
                            section=first_line[:128] or None,
                            tokens=len(content), embedding=list(vector)))
    await session.commit()
    return len(chunks)
