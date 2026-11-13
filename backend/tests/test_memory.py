"""记忆抽取启发式、存取 roundtrip 与 memory API 归属校验。"""
from sqlalchemy import select

from app.models.user import User
from app.services.memory_service import extract_memories, list_memories, save_memories

from .test_auth_login import register_and_login


async def _user_id(db, email: str) -> int:
    return (await db.execute(select(User).where(User.email == email))).scalar_one().id


def test_extract_three_kinds_and_no_trigger():
    msgs = [
        "今天天气不错。我喜欢轻装徒步，走起来舒服",
        "我怕高反，太高海拔不去",
        "我不喜欢走夜路",
        "我的鞋码是43",
        "我有5年徒步经验",
        "请问雨崩怎么走？",
    ]
    facts = extract_memories(msgs)
    assert [f.kind for f in facts] == [
        "preference", "constraint", "constraint", "fact", "fact",
    ]
    # content = 含触发词的那一句（按 。？！ 切分）
    assert facts[0].content == "我喜欢轻装徒步，走起来舒服"
    assert facts[1].content == "我怕高反，太高海拔不去"
    assert all(f.confidence == 0.8 for f in facts)
    assert extract_memories(["请问雨崩怎么走？"]) == []


async def test_save_and_list_roundtrip(db):
    facts = extract_memories(["我喜欢轻装徒步", "我的鞋码是43"])
    n = await save_memories(db, 1, facts, source_session="s" * 32)
    assert n == 2
    rows = await list_memories(db, 1)
    assert len(rows) == 2
    assert {r.kind for r in rows} == {"preference", "fact"}
    assert all(r.source_session == "s" * 32 and r.confidence == 0.8 for r in rows)
    # 其他用户查不到
    assert await list_memories(db, 2) == []


async def test_memory_api_list_and_delete_own(client, db):
    tokens = await register_and_login(client, email="m@b.com")
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    uid = await _user_id(db, "m@b.com")
    await save_memories(db, uid, extract_memories(["我喜欢轻装徒步", "我的鞋码是43"]))

    r = await client.get("/assistant/memory", headers=h)
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    assert set(items[0]) == {"id", "kind", "content", "confidence", "created_at"}

    mid = items[0]["id"]
    r = await client.delete(f"/assistant/memory/{mid}", headers=h)
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert len((await client.get("/assistant/memory", headers=h)).json()) == 1


async def test_delete_other_users_memory_404(client, db):
    ta = await register_and_login(client, email="ma@b.com")
    tb = await register_and_login(client, email="mb@b.com")
    ha = {"Authorization": f"Bearer {ta['access_token']}"}
    hb = {"Authorization": f"Bearer {tb['access_token']}"}
    uid_a = await _user_id(db, "ma@b.com")
    await save_memories(db, uid_a, extract_memories(["我爱骑行"]))

    mid = (await client.get("/assistant/memory", headers=ha)).json()[0]["id"]
    # B 删 A 的记忆 → 404，且 A 的记忆仍在
    assert (await client.delete(f"/assistant/memory/{mid}", headers=hb)).status_code == 404
    assert len((await client.get("/assistant/memory", headers=ha)).json()) == 1
