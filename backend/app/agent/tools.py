"""工具注册表与执行：助手 function-calling 的服务端落地。

生产替换票：check_weather / check_alerts 当前返回确定性假数据，
接入真实天气/预警源时替换对应实现，保持 TOOL_SPECS 与返回结构不变。
"""

from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import ToolSpec
from app.domains.sports import match_service, profile_service, route_service
from app.models.gear import UserGear
from app.models.route import Route
from app.models.user import User

TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="search_routes",
        description="按条件搜索徒步路线并按用户匹配度排序",
        parameters={
            "type": "object",
            "properties": {
                "sport": {"type": "string"},
                "region": {"type": "string"},
                "difficulty_max": {"type": "integer"},
            },
            "required": [],
        },
    ),
    ToolSpec(
        name="check_weather",
        description="查询目的地天气",
        parameters={
            "type": "object",
            "properties": {"loc": {"type": "string"}},
            "required": ["loc"],
        },
    ),
    ToolSpec(
        name="check_alerts",
        description="查询目的地灾害预警",
        parameters={
            "type": "object",
            "properties": {"loc": {"type": "string"}},
            "required": ["loc"],
        },
    ),
]

TOOL_REGISTRY: dict[str, ToolSpec] = {spec.name: spec for spec in TOOL_SPECS}


async def _search_routes(session: AsyncSession, user: User, arguments: dict) -> dict:
    routes: list[Route] = await route_service.list_routes(
        session,
        sport=arguments.get("sport"),
        region=arguments.get("region"),
        difficulty_max=arguments.get("difficulty_max"),
    )
    profile = await profile_service.get_or_create(session, user.id)
    gear_keys = {
        r.item_key
        for r in (await session.execute(select(UserGear).where(UserGear.user_id == user.id))).scalars()
    }
    scored: list[tuple[int, dict]] = []
    for r in routes:
        match = match_service.match_score(
            {"sports": profile.sports, "fitness": profile.fitness}, r, gear_keys
        )
        scored.append(
            (
                match,
                {
                    "id": r.id,
                    "name": r.name,
                    "region": r.region,
                    "sport": r.sport,
                    "difficulty": r.difficulty,
                    "distance_km": r.distance_km,
                    "climb_m": r.climb_m,
                    "duration_h": r.duration_h,
                    "clarity": r.clarity,
                    "match": match,
                },
            )
        )
    scored.sort(key=lambda t: t[0], reverse=True)
    return {"cards": [card for _, card in scored]}


async def _check_weather(session: AsyncSession, user: User, arguments: dict) -> dict:
    loc = arguments.get("loc")
    if not loc:
        raise ValueError("缺少参数 loc")
    return {"loc": loc, "temp_c": [12, 19], "cond": "多云", "rain_prob": 0.2}


async def _check_alerts(session: AsyncSession, user: User, arguments: dict) -> dict:
    loc = arguments.get("loc")
    if not loc:
        raise ValueError("缺少参数 loc")
    return {"loc": loc, "alerts": []}


_HANDLERS: dict[str, Callable[..., Awaitable[dict]]] = {
    "search_routes": _search_routes,
    "check_weather": _check_weather,
    "check_alerts": _check_alerts,
}


async def execute_tool(session: AsyncSession, user: User, name: str, arguments: dict) -> dict:
    if name not in TOOL_REGISTRY:
        raise ValueError("未知工具")
    return await _HANDLERS[name](session, user, arguments)
