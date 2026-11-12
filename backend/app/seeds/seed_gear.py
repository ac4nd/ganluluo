import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import Base, SessionLocal, engine
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
    # gear_models/user_gear have no alembic revision yet (out of Task 7 scope),
    # so the standalone seed ensures they exist before upserting into dev.db.
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[Base.metadata.tables["gear_models"], Base.metadata.tables["user_gear"]],
        )
    async with SessionLocal() as session:
        print("seeded:", await seed(session))


if __name__ == "__main__":
    asyncio.run(main())
