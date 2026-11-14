from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.admin.quota_service import get_status, record_usage, seed_tiers
from app.models.quota import QuotaTier
from app.models.user import User


async def _make_user(session: AsyncSession, email: str = "q@b.com") -> User:
    u = User(email=email, nickname="q", password_hash="x")
    session.add(u)
    await session.commit()  # fixture session keeps attributes after commit
    await session.refresh(u)
    return u


async def test_status_counts_and_limits(db):
    u = await _make_user(db)
    for _ in range(3):
        await record_usage(db, u.id, "s1", "m", 100, 50)
    st = await get_status(db, u.id, "trial")
    assert st.daily_chats_used == 3 and st.daily_chats_limit == 5
    assert st.daily_tokens_used == 450 and st.daily_tokens_limit == 20000
    assert st.allowed is True


async def test_status_over_limit(db):
    u = await _make_user(db, email="q2@b.com")
    for _ in range(6):
        await record_usage(db, u.id, "s2", "m", 5000, 1000)
    st = await get_status(db, u.id, "trial")
    assert st.allowed is False


async def test_tier_seed_idempotent(db):
    n1 = await seed_tiers(db)
    n2 = await seed_tiers(db)
    assert n1 >= 2 and n2 == 0
    rows = {t.tier: t for t in await db.scalars(select(QuotaTier))}
    assert rows["trial"].daily_chats == 5 and rows["trial"].daily_tokens == 20000
    assert rows["vip"].daily_chats == 50 and rows["vip"].daily_tokens == 500000


async def test_status_falls_back_without_tier_row(db):
    # 未 seed：quota_tiers 空表 → get_status 用默认 trial 限额（5/20000）兜底
    u = await _make_user(db, email="q3@b.com")
    st = await get_status(db, u.id, "trial")
    assert st.daily_chats_limit == 5 and st.daily_tokens_limit == 20000
    assert st.daily_chats_used == 0 and st.daily_tokens_used == 0
    assert st.allowed is True
