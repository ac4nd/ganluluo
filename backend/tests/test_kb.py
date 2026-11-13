from app.agent.chunker import chunk_text
from app.agent.embedder import FakeEmbedder
from app.agent.kb_service import ingest_document


def test_chunker_respects_size_and_overlap():
    text = "。".join(f"第{i}段" + "字" * 200 for i in range(5))
    chunks = chunk_text(text, size=300, overlap=50)
    assert all(len(c) <= 300 + 50 for c in chunks)
    assert len(chunks) >= 3


def test_fake_embedder_deterministic_1024():
    e1 = FakeEmbedder().embed(["徒步徽杭古道"])
    e2 = FakeEmbedder().embed(["徒步徽杭古道"])
    assert len(e1[0]) == 1024 and e1 == e2
    assert abs(sum(x * x for x in e1[0]) - 1.0) < 1e-6  # 归一化


async def test_ingest_idempotent(db):
    text = "徽杭古道攻略。" + "内容" * 400
    n1 = await ingest_document(db, source_name="徽杭古道攻略", text=text, sport="hiking")
    n2 = await ingest_document(db, source_name="徽杭古道攻略", text=text, sport="hiking")
    assert n1 > 0 and n2 == 0
