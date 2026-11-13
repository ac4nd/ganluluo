# tests/test_knowledge_search.py
from app.services.kb_service import ingest_document
from app.services.knowledge_service import search


async def test_search_hits_right_doc(db):
    await ingest_document(db, source_name="雨崩攻略", text="雨崩徒步 梅里雪山 冰湖 神瀑 高原反应注意事项 " + "雨崩" * 300, sport="hiking")
    await ingest_document(db, source_name="虎跳峡攻略", text="虎跳峡高路徒步 金沙江峡谷 龙洞瀑布 悬崖碎石 " + "虎跳峡" * 300, sport="hiking")
    hits = await search(db, "梅里雪山 冰湖 怎么走")
    assert hits and hits[0]["source_name"] == "雨崩攻略"
    assert len(hits) <= 4


async def test_search_empty_kb(db):
    assert await search(db, "随便") == []
