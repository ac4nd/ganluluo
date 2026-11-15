"""POST /assistant/plan：一键从对话澄清槽位生成行程计划。

回退顺序：显式入参 > 会话澄清槽位（sport/region/date）> 默认值（meet_at 08:00）。
会话经 session_store.own_session 归属校验，不存在/属于他人一律按无会话处理（422）。
选线复用 tools.search_routes_for（检索+match 评分，取 top1），落库与卡片组装经
trip_service，与 /trips 同构（装备提醒同样计算），不直查业务表。
"""

from datetime import date as _date
from datetime import time as _time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.assistant import session_store, tools
from app.assistant.clarify import parse_date_text
from app.core.db import get_session
from app.domains.sports import trip_service
from app.domains.sports.trip_schemas import TripPlanCard
from app.models.user import User

router = APIRouter()

DEFAULT_MEET_AT = _time(8, 0)


class PlanIn(BaseModel):
    # date/meet_at 字段名与类型同名：类体内带默认值的赋值先于注解求值绑定同名
    # 本地名（CPython 对 annotated assignment 先 STORE_NAME 再算注解），会遮蔽
    # 模块级类型导致 None | None，故注解经别名引用（运行时类型不变）。
    session_id: str | None = None
    route_id: int | None = None
    date: _date | None = None
    meet_at: _time | None = None
    # 与 TripPlanIn 一致：PG trip_plans.meet_place 为 VARCHAR(96)，超长应在校验层 422，
    # 而非直达 INSERT 报 StringDataRightTruncation → 500。
    meet_place: str | None = Field(None, max_length=96)


async def _own_slots(session: AsyncSession, user: User, session_id: str | None) -> dict[str, str]:
    """本人会话的澄清槽位；session_id 缺省/会话不存在或属于他人 → 空槽位。"""
    if session_id is None:
        return {}
    sess = await session_store.own_session(session, user.id, session_id)
    clarify = sess.clarify if sess is not None else None
    slots = clarify.get("slots") if isinstance(clarify, dict) else None
    return slots or {}


@router.post("/plan", response_model=TripPlanCard)
async def generate_plan(
    data: PlanIn,
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TripPlanCard:
    slots = await _own_slots(session, current, data.session_id)

    # 1. 路线：显式 route_id 优先；否则按槽位 sport/region 检索+评分取 top1。
    route_id = data.route_id
    if route_id is None:
        sport, region = slots.get("sport"), slots.get("region")
        if not sport and not region:  # 无会话或无可用检索槽位
            raise HTTPException(status_code=422, detail="无法确定路线")
        cards = await tools.search_routes_for(session, current, sport=sport, region=region)
        if not cards:  # 过滤后无候选（如槽位 sport 无任何路线）
            raise HTTPException(status_code=404, detail="无匹配路线")
        route_id = cards[0]["id"]

    # 2. 日期：显式 date 优先；否则解析槽位 date 文本。
    plan_date = data.date
    if plan_date is None:
        raw = slots.get("date")
        plan_date = parse_date_text(raw) if raw else None
        if plan_date is None:
            raise HTTPException(status_code=422, detail="无法确定日期")

    # 3. 集合时间缺省 08:00（不与 midnight 的 falsy 混淆，显式判 None）。
    meet_at = data.meet_at if data.meet_at is not None else DEFAULT_MEET_AT

    # 4. 落库（route published 校验在 service）→ 返回与 /trips 同构的计划卡。
    try:
        plan = await trip_service.create_plan(
            session, current.id, route_id, plan_date, meet_at, data.meet_place
        )
    except ValueError as e:  # 路线不存在或未发布
        raise HTTPException(status_code=404, detail=str(e)) from None
    owned = await trip_service.owned_gear_keys(session, current.id)
    return await trip_service.build_card(session, plan, owned)
