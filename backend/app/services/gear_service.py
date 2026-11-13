from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gear import GearModel, UserGear
from app.schemas.gear import GearItemIn, GearItemOut
from app.services.gear_catalog import CATEGORIES, ITEMS


async def get_catalog(session: AsyncSession) -> dict:
    rows = (await session.execute(select(GearModel))).scalars().all()
    by_item: dict[str, list[dict]] = {}
    for r in rows:
        by_item.setdefault(r.item_key, []).append({"id": r.id, "brand": r.brand, "model": r.model, "spec": r.spec})
    items = [{**it, "models": by_item.get(it["key"], [])} for it in ITEMS if by_item.get(it["key"])]
    return {"categories": CATEGORIES, "items": items}


async def get_gear_list(session: AsyncSession, user_id: int) -> list[GearItemOut]:
    rows = (await session.execute(select(UserGear).where(UserGear.user_id == user_id))).scalars().all()
    return [GearItemOut(item_key=r.item_key, model_id=r.model_id, custom_name=r.custom_name) for r in rows]


async def replace_gear_list(session: AsyncSession, user_id: int, items: list[GearItemIn]) -> list[GearItemOut]:
    # Validate the whole payload BEFORE touching state: a bad row used to fail
    # mid-loop after the delete had already fired, surfacing as a 500 with the
    # user's list wiped. Unknown keys/ids and duplicates now raise ValueError,
    # which the route maps to 422.
    valid_keys = {it["key"] for it in ITEMS}
    seen: set[tuple[str, int | None]] = set()
    model_ids = {m.id for m in (await session.execute(select(GearModel))).scalars()}
    for it in items:
        if it.item_key not in valid_keys:
            raise ValueError(f"未知装备类型: {it.item_key}")
        if it.model_id is not None and it.model_id not in model_ids:
            raise ValueError(f"未知型号 id: {it.model_id}")
        key = (it.item_key, it.model_id)
        if key in seen:
            raise ValueError(f"重复条目: {it.item_key} #{it.model_id}")
        seen.add(key)
    await session.execute(delete(UserGear).where(UserGear.user_id == user_id))
    for it in items:
        session.add(UserGear(user_id=user_id, item_key=it.item_key, model_id=it.model_id, custom_name=it.custom_name))
    await session.commit()
    rows = (await session.execute(select(UserGear).where(UserGear.user_id == user_id))).scalars().all()
    return [GearItemOut(item_key=r.item_key, model_id=r.model_id, custom_name=r.custom_name) for r in rows]
