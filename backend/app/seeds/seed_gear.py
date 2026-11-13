import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.models.gear import GearModel
from app.services.gear_catalog import MODELS


async def seed(session: AsyncSession) -> int:
    added = 0
    for item_key, entries in MODELS.items():
        for brand, model, spec in entries:
            exists = (await session.execute(
                select(GearModel).where(GearModel.item_key == item_key,
                                        GearModel.brand == brand, GearModel.model == model)
            )).scalar_one_or_none()
            if exists is None:
                session.add(GearModel(item_key=item_key, brand=brand, model=model, spec=spec))
                added += 1
    await session.commit()
    return added


async def main() -> None:
    # gear_models/user_gear come from alembic revision 0003; the seed only
    # upserts catalog rows into dev.db.
    async with SessionLocal() as session:
        print("seeded:", await seed(session))


if __name__ == "__main__":
    asyncio.run(main())
