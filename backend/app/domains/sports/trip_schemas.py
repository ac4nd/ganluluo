"""行程计划契约：/trips 与 /assistant/plan 共用的请求/响应模型。

TripPlanCard = TripPlanOut 基础字段 + 路线摘要 + 装备提醒，卡片组装函数见
trip_service（assistant 层只经本契约与 service 组装，不 import 路由模块）。
"""

from datetime import date, time

from pydantic import BaseModel, Field


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
