"""行程计划 API：/trips CRUD + 计划卡（路线摘要 + 装备提醒）。

装备提醒：route.required_gear − 用户 user_gear.item_keys。契约与卡片组装下沉在
trip_schemas / trip_service（M4 Task 3，/assistant/plan 共用），路由层只做 HTTP 编排。
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.domains.sports import trip_service
from app.domains.sports.trip_schemas import TripPlanCard, TripPlanIn, TripStatusIn
from app.models.user import User

router = APIRouter()


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
    owned = await trip_service.owned_gear_keys(session, current.id)
    return await trip_service.build_card(session, plan, owned)


@router.get("", response_model=list[TripPlanCard])
async def list_trips(
    status: str | None = Query(None, description="按状态过滤：planned/done/cancelled"),
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[TripPlanCard]:
    if status is not None and status not in ("planned", "done", "cancelled"):
        raise HTTPException(status_code=422, detail="非法行程状态")
    plans = await trip_service.list_plans(session, current.id, status=status)
    routes = await trip_service.routes_map(session, plans)
    owned = await trip_service.owned_gear_keys(session, current.id)
    return [trip_service.to_card(p, routes[p.route_id], owned) for p in plans]


@router.get("/{trip_id}", response_model=TripPlanCard)
async def get_trip(
    trip_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TripPlanCard:
    plan = await trip_service.get_plan(session, current.id, trip_id)
    if plan is None:  # 不存在或非本人
        raise HTTPException(status_code=404, detail="行程不存在")
    owned = await trip_service.owned_gear_keys(session, current.id)
    return await trip_service.build_card(session, plan, owned)


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
    owned = await trip_service.owned_gear_keys(session, current.id)
    return await trip_service.build_card(session, plan, owned)


@router.delete("/{trip_id}", status_code=204)
async def delete_trip(
    trip_id: int,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    if not await trip_service.delete_plan(session, current.id, trip_id):
        raise HTTPException(status_code=404, detail="行程不存在")
