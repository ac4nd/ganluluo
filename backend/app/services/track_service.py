from dataclasses import dataclass

import gpxpy
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.route import Route
from app.services.geo import (
    clarity_from_stats,
    difficulty_from_stats,
    douglas_peucker,
    haversine_m,
    points_to_elevation_profile,
    total_climb_m,
)

MAX_TRACK_POINTS = 500


@dataclass
class TrackSummary:
    points: int
    distance_km: float
    climb_m: int
    difficulty: int
    clarity: str


def parse_gpx_points(gpx_text: str) -> list[tuple[float, float, float | None]]:
    gpx = gpxpy.parse(gpx_text)
    pts: list[tuple[float, float, float | None]] = []
    for track in gpx.tracks:
        for seg in track.segments:
            for p in seg.points:
                pts.append((p.latitude, p.longitude, p.elevation))
    return pts


async def process_track(session: AsyncSession, route: Route, gpx_text: str) -> TrackSummary:
    raw = parse_gpx_points(gpx_text)
    if len(raw) < 2:
        raise ValueError("轨迹点不足")
    coords = [(lat, lon) for lat, lon, _ in raw]
    eles = [e for _, _, e in raw]
    simple = douglas_peucker(coords, eps_m=8.0)
    dist_m = sum(
        haversine_m(simple[i][0], simple[i][1], simple[i + 1][0], simple[i + 1][1])
        for i in range(len(simple) - 1)
    )
    distance_km = round(dist_m / 1000, 2)
    climb = total_climb_m(eles, threshold_m=10)
    difficulty = difficulty_from_stats(distance_km, climb)
    clarity = clarity_from_stats(len(raw), distance_km)
    # 简化点对齐高程（最近邻原始点高程），上限 500 点。douglas_peucker 返回的是
    # 输入点集的真子集，故可用 (lat, lon) -> ele 哈希表 O(1) 查表，替代全量线性扫描。
    ele_by_coord: dict[tuple[float, float], float | None] = {(la, lo): e for la, lo, e in raw}

    def nearest_ele(lat: float, lon: float) -> float | None:
        return ele_by_coord.get((lat, lon))
    kept: list[tuple[float, float, float | None]] = []
    if len(simple) <= MAX_TRACK_POINTS:
        kept = [(la, lo, nearest_ele(la, lo)) for la, lo in simple]
    else:
        # 均匀采样前 499 个点，末尾强制保留轨迹终点（总数不超过 500 点上限）。
        step = len(simple) / MAX_TRACK_POINTS
        for i in range(MAX_TRACK_POINTS - 1):
            la, lo = simple[int(i * step)]
            kept.append((la, lo, nearest_ele(la, lo)))
        if simple[-1] != kept[-1][:2]:
            kept.append((simple[-1][0], simple[-1][1], nearest_ele(simple[-1][0], simple[-1][1])))
    route.track_points = [{"lat": la, "lon": lo, "ele": e} for la, lo, e in kept]
    route.elevation = points_to_elevation_profile([(la, lo, e) for la, lo, e in kept])
    route.distance_km = distance_km
    route.climb_m = climb
    route.difficulty = difficulty
    route.clarity = clarity
    await session.commit()
    return TrackSummary(points=len(raw), distance_km=distance_km, climb_m=climb,
                        difficulty=difficulty, clarity=clarity)
