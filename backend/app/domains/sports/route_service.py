from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.sports.route_schemas import RouteIn
from app.models.route import Route

_VALID_SORTS = {"new", "points"}


async def list_routes(session: AsyncSession, sport: str | None = None, region: str | None = None,
                      difficulty_max: int | None = None, clarity: str | None = None,
                      created_after: str | None = None, sort: str | None = None) -> list[Route]:
    if sort is not None and sort not in _VALID_SORTS:
        raise ValueError("非法排序方式")
    stmt = select(Route).where(Route.status == "published")
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
    if created_after:
        try:
            day = datetime.strptime(created_after, "%Y-%m-%d")
        except ValueError:
            raise ValueError("时间格式应为 YYYY-MM-DD") from None
        # naive 零点：created_at 列在 SQLite 存字符串、PG 带 tz，均可直接比较
        stmt = stmt.where(Route.created_at >= datetime(day.year, day.month, day.day))
    if sort == "new":
        stmt = stmt.order_by(Route.created_at.desc(), Route.id.desc())
    else:
        # 默认与 points 均保持 id 升序（points 的 python 稳定排序依赖它）
        stmt = stmt.order_by(Route.id)
    rows = list((await session.execute(stmt)).scalars().all())
    if sort == "points":
        # MVP 数据量小：SQL 按 id 序取回后，python 稳定排序按轨迹点数降序
        # （无轨迹排后；跨方言 JSON 长度函数不值得）
        rows.sort(key=lambda r: len(r.track_points or []), reverse=True)
    return rows


async def get_route(session: AsyncSession, route_id: int) -> Route | None:
    return (await session.execute(select(Route).where(Route.id == route_id))).scalar_one_or_none()


async def create_route(session: AsyncSession, data: RouteIn) -> Route:
    route = Route(**data.model_dump())
    route.source = "user"
    session.add(route)
    await session.commit()
    await session.refresh(route)
    return route
