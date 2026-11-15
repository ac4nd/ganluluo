from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.sports.route_schemas import RouteIn
from app.models.route import Route


async def list_routes(session: AsyncSession, sport: str | None = None, region: str | None = None,
                      difficulty_max: int | None = None, clarity: str | None = None) -> list[Route]:
    stmt = select(Route).where(Route.status == "published").order_by(Route.id)
    if sport:
        stmt = stmt.where(Route.sport == sport)
    if region:
        # region 关键词同时匹配地区列与路线名（"雨崩/虎跳峡"等词只出现在
        # 路线名里，clarify 抽取的 region 槽位才能命中）。
        stmt = stmt.where(Route.region.ilike(f"%{region}%") | Route.name.ilike(f"%{region}%"))
    if difficulty_max:
        stmt = stmt.where(Route.difficulty <= difficulty_max)
    if clarity:
        stmt = stmt.where(Route.clarity == clarity)
    return list((await session.execute(stmt)).scalars().all())


async def get_route(session: AsyncSession, route_id: int) -> Route | None:
    return (await session.execute(select(Route).where(Route.id == route_id))).scalar_one_or_none()


async def create_route(session: AsyncSession, data: RouteIn) -> Route:
    route = Route(**data.model_dump())
    route.source = "user"
    session.add(route)
    await session.commit()
    await session.refresh(route)
    return route
