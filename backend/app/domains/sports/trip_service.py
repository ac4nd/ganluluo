"""行程计划服务：MVP 单表 trip_plans，一行 = 一次出行（路线 × 日期 × 集合点）。

assistant 层（/assistant/plan）只经本模块函数创建计划，不直查业务表。
"""

from datetime import date, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.route import Route
from app.models.trip import TripPlan

VALID_STATUSES = {"planned", "done", "cancelled"}


async def create_plan(
    session: AsyncSession,
    user_id: int,
    route_id: int,
    date: date,
    meet_at: time,
    meet_place: str | None = None,
) -> TripPlan:
    """创建行程计划；route 必须存在且已发布。"""
    route = await session.get(Route, route_id)
    if route is None or route.status != "published":
        raise ValueError("路线不存在或未发布")
    plan = TripPlan(
        user_id=user_id, route_id=route_id, date=date, meet_at=meet_at, meet_place=meet_place
    )
    session.add(plan)
    await session.commit()  # fixture session keeps attributes after commit
    return plan


async def list_plans(session: AsyncSession, user_id: int) -> list[TripPlan]:
    """按 (status=='planned') desc, date asc 排序：未来计划在前，同组内按日期升序。"""
    result = await session.execute(
        select(TripPlan)
        .where(TripPlan.user_id == user_id)
        .order_by((TripPlan.status == "planned").desc(), TripPlan.date.asc())
    )
    return list(result.scalars().all())


async def get_plan(session: AsyncSession, user_id: int, plan_id: int) -> TripPlan | None:
    """按 id 取计划，归属校验：不存在或非本人 → None。"""
    plan = await session.get(TripPlan, plan_id)
    if plan is None or plan.user_id != user_id:
        return None
    return plan


async def set_status(
    session: AsyncSession, user_id: int, plan_id: int, status: str
) -> TripPlan | None:
    """更新计划状态；status 非法 → ValueError，不存在/非本人 → None。"""
    if status not in VALID_STATUSES:
        raise ValueError("非法行程状态")
    plan = await get_plan(session, user_id, plan_id)
    if plan is None:
        return None
    plan.status = status
    await session.commit()
    return plan


async def delete_plan(session: AsyncSession, user_id: int, plan_id: int) -> bool:
    """删除计划：不存在/非本人 → False，删除成功 → True。"""
    plan = await get_plan(session, user_id, plan_id)
    if plan is None:
        return False
    await session.delete(plan)
    await session.commit()
    return True
