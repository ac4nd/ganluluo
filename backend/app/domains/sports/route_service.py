from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.route import Route
from app.domains.sports.route_schemas import RouteIn


async def list_routes(session: AsyncSession, sport: str | None = None, region: str | None = None,
                      difficulty_max: int | None = None, clarity: str | None = None) -> list[Route]:
    stmt = select(Route).where(Route.status == "published").order_by(Route.id)
    if sport:
        stmt = stmt.where(Route.sport == sport)
    if region:
        stmt = stmt.where(Route.region.ilike(f"%{region}%"))
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
