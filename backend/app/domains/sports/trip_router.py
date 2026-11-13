"""行程计划 API：/trips CRUD + 计划卡（路线摘要 + 装备提醒）。

装备提醒：route.required_gear − 用户 user_gear.item_keys。service 返回 ORM 行，
路线摘要与装备差集在路由层组装为 TripPlanCard（user_gear 属 sports 域内数据，直查）。
"""

from datetime import date, time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.domains.sports import trip_service
from app.models.gear import UserGear
from app.models.route import Route
from app.models.trip import TripPlan
from app.models.user import User

router = APIRouter()


class TripPlanIn(BaseModel):
    route_id: int
    date: date
    meet_at: time
    meet_place: str | None = Field(None, max_length=96)


class TripStatusIn(BaseModel):
    status: str


class TripPlanOut(BaseModel):
    id: int
    user_id: int
    route_id: int
    date: date
    meet_at: time
    meet_place: str | None
    status: str
    model_config = {"from_attributes": True}


class TripPlanCard(TripPlanOut):
    route_name: str
    region: str
    sport: str
    difficulty: int
    distance_km: float
    climb_m: int
    duration_h: float | None
    gear_missing: list[str]


async def _owned_gear_keys(session: AsyncSession, user_id: int) -> set[str]:
    """用户已有装备键集合（取法同 app/assistant/tools.py 的 search_routes）。"""
    rows = await session.execute(select(UserGear.item_key).where(UserGear.user_id == user_id))
    return set(rows.scalars())


def _gear_missing(route: Route, owned: set[str]) -> list[str]:
    return [g for g in (route.required_gear or []) if g not in owned]


def _to_card(plan: TripPlan, route: Route, owned: set[str]) -> TripPlanCard:
    base = TripPlanOut.model_validate(plan).model_dump()
    return TripPlanCard(
        **base,
        route_name=route.name,
        region=route.region,
        sport=route.sport,
        difficulty=route.difficulty,
        distance_km=route.distance_km,
        climb_m=route.climb_m,
        duration_h=route.duration_h,
        gear_missing=_gear_missing(route, owned),
    )


async def _routes_map(session: AsyncSession, plans: list[TripPlan]) -> dict[int, Route]:
    """按计划的 route_id 批量取路线（计划行均由 FK 保证路线存在）。"""
    rows = await session.execute(select(Route).where(Route.id.in_([p.route_id for p in plans])))
    return {r.id: r for r in rows.scalars()}


@router.post("", response_model=TripPlanCard, status_code=201)
async def create_trip(
    data: TripPlanIn,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TripPlanCard:
    try:
        plan = await trip_service.create_plan(
            session, current.id, data.route_id, data.date, data.meet_at, data.meet_place
        )
    except ValueError as e:  # 路线不存在或未发布
        raise HTTPException(status_code=404, detail=str(e)) from None
    owned = await _owned_gear_keys(session, current.id)
    return _to_card(plan, (await _routes_map(session, [plan]))[plan.route_id], owned)


@router.get("", response_model=list[TripPlanCard])
async def list_trips(
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[TripPlanCard]:
    plans = await trip_service.list_plans(session, current.id)
    routes = await _routes_map(session, plans)
    owned = await _owned_gear_keys(session, current.id)
    return [_to_card(p, routes[p.route_id], owned) for p in plans]


@router.get("/{trip_id}", response_model=TripPlanCard)
async def get_trip(
    trip_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TripPlanCard:
    plan = await trip_service.get_plan(session, current.id, trip_id)
    if plan is None:  # 不存在或非本人
        raise HTTPException(status_code=404, detail="行程不存在")
    owned = await _owned_gear_keys(session, current.id)
    return _to_card(plan, (await _routes_map(session, [plan]))[plan.route_id], owned)


@router.patch("/{trip_id}/status", response_model=TripPlanCard)
async def update_trip_status(
    trip_id: int,
    data: TripStatusIn,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TripPlanCard:
    # 先查归属（404 优先于非法枚举 400）：归属成立后 set_status 的 ValueError 只会是非法状态。
    if await trip_service.get_plan(session, current.id, trip_id) is None:
        raise HTTPException(status_code=404, detail="行程不存在")
    try:
        plan = await trip_service.set_status(session, current.id, trip_id, data.status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    assert plan is not None  # 上一行已确认归属
    owned = await _owned_gear_keys(session, current.id)
    return _to_card(plan, (await _routes_map(session, [plan]))[plan.route_id], owned)


@router.delete("/{trip_id}", status_code=204)
async def delete_trip(
    trip_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    if not await trip_service.delete_plan(session, current.id, trip_id):
        raise HTTPException(status_code=404, detail="行程不存在")
