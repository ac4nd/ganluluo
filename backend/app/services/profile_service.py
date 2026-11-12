from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import UserProfile
from app.schemas.profile import ProfileIn


async def get_or_create(session: AsyncSession, user_id: int) -> UserProfile:
    row = (await session.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )).scalar_one_or_none()
    if row is None:
        row = UserProfile(user_id=user_id)
        session.add(row)
        await session.commit()
    return row


async def update(session: AsyncSession, user_id: int, data: ProfileIn) -> UserProfile:
    row = await get_or_create(session, user_id)
    row.sports = [s.value for s in data.sports]
    row.exp_level = data.exp_level
    row.fitness = data.fitness
    await session.commit()
    return row
