"""混合检索：词面 bigram Jaccard + 嵌入余弦 → RRF 融合 → bigram 重叠度重排。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.embedder import Embedder, get_embedder
from app.models.kb import KbChunk, KbDoc

RRF_K = 60


def _bigrams(text: str) -> set[str]:
    """字符 bigram 集合：相邻两字符为一个单元。"""
    return {text[i:i + 2] for i in range(len(text) - 1)}


def _cosine(a: list[float], b: list[float]) -> float:
    """余弦相似度；任一向量零范数（或长度不重叠）时记 0。"""
    dot = sum(x * y for x, y in zip(a, b))
    norm = (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5)
    return dot / norm if norm else 0.0


async def search(session: AsyncSession, query: str, k: int = 8, final_k: int = 4,
                 sport: str | None = None, embedder: Embedder | None = None) -> list[dict]:
    """混合检索：返回 [{doc_id, source_name, chunk_no, content, score, sport}]。

    词面 = 查询与块内容的字符 bigram Jaccard；向量 = 查询与块嵌入的余弦；
    RRF(k1=60) 融合两路排名（score = Σ 1/(60+rank)，未上榜一路贡献 0）；
    取 RRF 前 k 个候选，按查询/块 bigram 重叠数降序稳定重排，返回前 final_k。
    score 即重排重叠数（float）。空库返回 []。
    """
    stmt = (select(KbChunk, KbDoc.source_name)
            .join(KbDoc, KbDoc.id == KbChunk.doc_id)
            .order_by(KbChunk.id))
    if sport is not None:
        stmt = stmt.where(KbChunk.sport == sport)
    rows = (await session.execute(stmt)).all()
    if not rows:
        return []

    q_bigrams = _bigrams(query)
    q_vec = (embedder or get_embedder()).embed([query])[0]

    lexical: list[tuple[float, int]] = []  # (jaccard, 行号)，0 分不进榜
    vector: list[tuple[float, int]] = []   # (cosine, 行号)；None/零嵌入跳过
    for idx, (chunk, _source_name) in enumerate(rows):
        c_bigrams = _bigrams(chunk.content)
        union = q_bigrams | c_bigrams
        if union:
            jaccard = len(q_bigrams & c_bigrams) / len(union)
            if jaccard > 0.0:
                lexical.append((jaccard, idx))
        if chunk.embedding is not None:
            cosine = _cosine(q_vec, list(chunk.embedding))
            if cosine > 0.0:
                vector.append((cosine, idx))

    rrf = [0.0] * len(rows)
    for ranking in (lexical, vector):
        ranked = sorted(ranking, key=lambda item: -item[0])  # 稳定排序，平分按行序
        for rank, (_score, idx) in enumerate(ranked, start=1):
            rrf[idx] += 1.0 / (RRF_K + rank)

    candidates = sorted(range(len(rows)), key=lambda i: -rrf[i])[:k]
    reranked = sorted(candidates,
                      key=lambda i: -len(q_bigrams & _bigrams(rows[i][0].content)))

    hits: list[dict] = []
    for idx in reranked[:final_k]:
        chunk, source_name = rows[idx]
        hits.append({
            "doc_id": chunk.doc_id,
            "source_name": source_name,
            "chunk_no": chunk.chunk_no,
            "content": chunk.content,
            "score": float(len(q_bigrams & _bigrams(chunk.content))),
            "sport": chunk.sport,
        })
    return hits
