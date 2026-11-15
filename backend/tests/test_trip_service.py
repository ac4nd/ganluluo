from datetime import date, time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.sports import trip_service
from app.models.route import Route
from app.models.trip import TripPlan
from app.models.user import User


async def _make_user(db: AsyncSession, email: str) -> User:
    user = User(email=email, nickname=email.split("@")[0])
    db.add(user)
    await db.commit()
    return user


async def _make_route(db: AsyncSession, status: str = "published") -> Route:
    route = Route(name="梅里东环", region="迪庆", sport="hiking", difficulty=2,
                  distance_km=12.5, climb_m=600, clarity="mid", status=status)
    db.add(route)
    await db.commit()
    return route


async def test_create_plan_success(db):
    user = await _make_user(db, "plan@b.com")
    route = await _make_route(db)
    plan = await trip_service.create_plan(
        db, user.id, route.id, date(2026, 11, 20), time(8, 30), meet_place="飞来寺观景台"
    )
    assert plan.id is not None
    assert plan.user_id == user.id
    assert plan.route_id == route.id
    assert plan.date == date(2026, 11, 20)
    assert plan.meet_at == time(8, 30)
    assert plan.meet_place == "飞来寺观景台"
    assert plan.status == "planned"


async def test_create_plan_route_not_found(db):
    user = await _make_user(db, "ghost@b.com")
    with pytest.raises(ValueError, match="路线不存在或未发布"):
        await trip_service.create_plan(db, user.id, 999, date(2026, 11, 20), time(8, 30))


async def test_create_plan_route_not_published(db):
    user = await _make_user(db, "draft@b.com")
    route = await _make_route(db, status="draft")
    with pytest.raises(ValueError, match="路线不存在或未发布"):
        await trip_service.create_plan(db, user.id, route.id, date(2026, 11, 20), time(8, 30))


async def test_list_plans_planned_first_then_by_date(db):
    user = await _make_user(db, "sort@b.com")
    route = await _make_route(db)
    # 乱序插入：planned(晚) → done(中) → planned(早) → cancelled(早)
    rows = [
        ("planned", date(2026, 11, 20)),
        ("done", date(2026, 11, 10)),
        ("planned", date(2026, 11, 15)),
        ("cancelled", date(2026, 11, 5)),
    ]
    for status, d in rows:
        plan = TripPlan(user_id=user.id, route_id=route.id, date=d, meet_at=time(8, 0))
        plan.status = status
        db.add(plan)
    await db.commit()

    plans = await trip_service.list_plans(db, user.id)
    assert [(p.status, p.date) for p in plans] == [
        ("planned", date(2026, 11, 15)),
        ("planned", date(2026, 11, 20)),
        ("cancelled", date(2026, 11, 5)),
        ("done", date(2026, 11, 10)),
    ]


async def test_list_plans_only_own(db):
    me = await _make_user(db, "me@b.com")
    other = await _make_user(db, "other@b.com")
    route = await _make_route(db)
    await trip_service.create_plan(db, other.id, route.id, date(2026, 11, 20), time(8, 0))
    mine = await trip_service.create_plan(db, me.id, route.id, date(2026, 11, 21), time(8, 0))
    plans = await trip_service.list_plans(db, me.id)
    assert [p.id for p in plans] == [mine.id]


async def test_get_plan_ownership(db):
    me = await _make_user(db, "get@b.com")
    other = await _make_user(db, "get2@b.com")
    route = await _make_route(db)
    plan = await trip_service.create_plan(db, me.id, route.id, date(2026, 11, 20), time(8, 0))
    assert await trip_service.get_plan(db, me.id, plan.id) is plan
    assert await trip_service.get_plan(db, other.id, plan.id) is None
    assert await trip_service.get_plan(db, me.id, 9999) is None


async def test_set_status_valid_and_invalid(db):
    user = await _make_user(db, "status@b.com")
    route = await _make_route(db)
    plan = await trip_service.create_plan(db, user.id, route.id, date(2026, 11, 20), time(8, 0))
    done = await trip_service.set_status(db, user.id, plan.id, "done")
    assert done is not None and done.status == "done"
    cancelled = await trip_service.set_status(db, user.id, plan.id, "cancelled")
    assert cancelled is not None and cancelled.status == "cancelled"
    back = await trip_service.set_status(db, user.id, plan.id, "planned")
    assert back is not None and back.status == "planned"
    with pytest.raises(ValueError):
        await trip_service.set_status(db, user.id, plan.id, "finished")


async def test_set_status_missing_or_not_owner_returns_none(db):
    me = await _make_user(db, "own@b.com")
    other = await _make_user(db, "own2@b.com")
    route = await _make_route(db)
    plan = await trip_service.create_plan(db, me.id, route.id, date(2026, 11, 20), time(8, 0))
    assert await trip_service.set_status(db, other.id, plan.id, "done") is None
    assert await trip_service.set_status(db, me.id, 9999, "done") is None


async def test_delete_plan_owner_and_not_owner(db):
    me = await _make_user(db, "del@b.com")
    other = await _make_user(db, "del2@b.com")
    route = await _make_route(db)
    plan = await trip_service.create_plan(db, me.id, route.id, date(2026, 11, 20), time(8, 0))
    assert await trip_service.delete_plan(db, other.id, plan.id) is False
    assert await trip_service.delete_plan(db, me.id, plan.id) is True
    assert await trip_service.delete_plan(db, me.id, plan.id) is False
    assert await trip_service.get_plan(db, me.id, plan.id) is None
