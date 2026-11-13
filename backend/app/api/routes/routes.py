from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.models.user import User
from app.schemas.route import RouteDetailOut, RouteIn, RouteOut, TrackSummaryOut
from app.services import route_service, track_service

router = APIRouter(prefix="/routes", tags=["routes"])


@router.get("", response_model=list[RouteOut])
async def list_routes(sport: str | None = None, region: str | None = None,
                      difficulty_max: int | None = None, clarity: str | None = None,
                      session: AsyncSession = Depends(get_session)) -> list[RouteOut]:
    rows = await route_service.list_routes(session, sport, region, difficulty_max, clarity)
    return [RouteOut.model_validate(r) for r in rows]


@router.get("/{route_id}", response_model=RouteDetailOut)
async def get_route(route_id: int, session: AsyncSession = Depends(get_session)) -> RouteDetailOut:
    route = await route_service.get_route(session, route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="路线不存在")
    return RouteDetailOut.model_validate(route)


@router.post("", response_model=RouteOut, status_code=201)
async def create_route(data: RouteIn, current: User = Depends(get_current_user),
                       session: AsyncSession = Depends(get_session)) -> RouteOut:
    route = await route_service.create_route(session, data)
    return RouteOut.model_validate(route)


@router.post("/{route_id}/track", response_model=TrackSummaryOut)
async def upload_track(route_id: int, request: Request,
                       session: AsyncSession = Depends(get_session)) -> TrackSummaryOut:
    route = await route_service.get_route(session, route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="路线不存在")
    body = (await request.body()).decode("utf-8", errors="replace")
    try:
        summary = await track_service.process_track(session, route, body)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    return TrackSummaryOut(points=summary.points, distance_km=summary.distance_km,
                           climb_m=summary.climb_m, difficulty=summary.difficulty,
                           clarity=summary.clarity)
