from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gear import GearModel
from app.services.gear_catalog import CATEGORIES, ITEMS


async def get_catalog(session: AsyncSession) -> dict:
    rows = (await session.execute(select(GearModel))).scalars().all()
    by_item: dict[str, list[dict]] = {}
    for r in rows:
        by_item.setdefault(r.item_key, []).append({"id": r.id, "brand": r.brand, "model": r.model, "spec": r.spec})
    items = [{**it, "models": by_item.get(it["key"], [])} for it in ITEMS if by_item.get(it["key"])]
    return {"categories": CATEGORIES, "items": items}
