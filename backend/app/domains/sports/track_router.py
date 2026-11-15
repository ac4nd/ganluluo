"""GPX 轨迹上传 API（M4.5-tracks Task 2）：POST /tracks 同步处理管线。

校验全部前置（后缀/大小/UTF-8 解码/≥2 点，任一失败 422 中文 detail），通过后才
写文件、落 route + route_track 两行，再同步 process_track 覆盖路线统计并置
processed=True。解析失败发生在任何落库/落盘之前，失败不留行。
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from gpxpy.gpx import GPXException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.db import get_session
from app.domains.auth.schemas import Sport
from app.domains.sports import track_service, track_store
from app.domains.sports.route_schemas import TrackOut
from app.models.route import Route
from app.models.track import RouteTrack
from app.models.user import User

router = APIRouter()

MAX_GPX_BYTES = 5 * 1024 * 1024  # 5MB 上限


@router.post("", response_model=TrackOut, status_code=201)
async def upload_track(
    name: str = Form(min_length=1, max_length=64),
    region: str = Form(min_length=1, max_length=64),
    sport: Sport = Form(...),
    file: UploadFile = File(...),
    current: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TrackOut:
    # —— 校验段：全部前置，任一失败 422，不落任何行/文件 ——
    if not (file.filename or "").lower().endswith(".gpx"):
        raise HTTPException(status_code=422, detail="仅支持 .gpx 文件")
    content = await file.read()
    if len(content) > MAX_GPX_BYTES:
        raise HTTPException(status_code=422, detail="轨迹文件超过 5MB 上限")
    try:
        gpx_text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="文件必须是 UTF-8 编码的文本") from None
    try:
        raw = track_service.parse_gpx_points(gpx_text)
    except (ValueError, GPXException) as e:
        raise HTTPException(status_code=422, detail=f"GPX 解析失败：{e}") from None
    if len(raw) < 2:
        raise HTTPException(status_code=422, detail="轨迹点不足")

    # —— 落盘段：写 GPX 并读回（防御性 404：正常时读刚写的文件不会缺）——
    key = track_store.save_gpx(content)
    try:
        gpx_text = track_store.read_gpx(key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="轨迹文件不存在") from None

    # —— 落库段：route + track 先 flush 拿 id；process_track 尾部 commit 一并
    # 持久化两行，其后再置 processed=True 补一次 commit（brief 流程 3）。
    # 中性占位列中 distance/climb/difficulty/clarity/track_points/elevation
    # 会被 process_track 覆盖，duration_h 与 terrain/pace 留空结构占位。
    route = Route(
        name=name,
        region=region,
        sport=sport.value,
        status="draft",
        difficulty=1,
        distance_km=0.0,
        climb_m=0,
        duration_h=0.0,
        clarity="low",
        terrain=[],
        pace=[],
    )
    session.add(route)
    await session.flush()
    track = RouteTrack(route_id=route.id, gpx_object=key, points=len(raw), processed=False)
    session.add(track)
    await session.flush()

    summary = await track_service.process_track(session, route, gpx_text)
    track.processed = True
    await session.commit()
    return TrackOut(route_id=route.id, track_id=track.id, points=summary.points,
                    distance_km=summary.distance_km, climb_m=summary.climb_m,
                    difficulty=summary.difficulty, clarity=summary.clarity)
