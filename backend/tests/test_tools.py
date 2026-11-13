import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import tools
from app.models.gear import UserGear
from app.models.user import User
from app.seeds.seed_routes import seed_routes


async def _make_user(db: AsyncSession, gear: list[str] | None = None) -> User:
    user = User(email="tool@b.com", nickname="tool")
    db.add(user)
    await db.commit()  # fixture session keeps attributes after commit
    for key in gear or []:
        db.add(UserGear(user_id=user.id, item_key=key))
    await db.commit()
    return user


async def test_search_routes_returns_cards_with_match(db):
    await seed_routes(db)
    user = await _make_user(db, gear=["boots", "rain-gear", "first-aid"])
    result = await tools.execute_tool(db, user, "search_routes", {"difficulty_max": 3})
    cards = result["cards"]
    assert cards
    for c in cards:
        assert set(c) == {
            "id",
            "name",
            "region",
            "sport",
            "difficulty",
            "distance_km",
            "climb_m",
            "duration_h",
            "clarity",
            "match",
        }
        assert isinstance(c["match"], int) and 0 <= c["match"] <= 100
        assert c["difficulty"] <= 3
        assert c["duration_h"] is None or isinstance(c["duration_h"], float)
        assert isinstance(c["clarity"], str)
    matches = [c["match"] for c in cards]
    assert matches == sorted(matches, reverse=True)


async def test_unknown_tool_raises(db):
    await seed_routes(db)
    user = await _make_user(db)
    with pytest.raises(ValueError, match="未知工具"):
        await tools.execute_tool(db, user, "nope", {})


def test_registry_and_handlers_are_in_sync():
    assert set(tools.TOOL_REGISTRY) == set(tools._HANDLERS)
    assert set(tools.TOOL_REGISTRY) == {spec.name for spec in tools.TOOL_SPECS}


async def test_weather_and_alerts_shape(db):
    await seed_routes(db)
    user = await _make_user(db)
    weather = await tools.execute_tool(db, user, "check_weather", {"loc": "梅里雪山"})
    assert weather == {"loc": "梅里雪山", "temp_c": [12, 19], "cond": "多云", "rain_prob": 0.2}
    alerts = await tools.execute_tool(db, user, "check_alerts", {"loc": "梅里雪山"})
    assert alerts == {"loc": "梅里雪山", "alerts": []}
