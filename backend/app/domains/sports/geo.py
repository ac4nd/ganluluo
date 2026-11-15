"""地理/轨迹纯函数库：距离、抽稀、爬升、难度与清晰度评分。

全部为无状态纯函数，便于单测与跨模块复用（assistant/route/worker 共用）。
"""
import math

_EARTH_R_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_R_M * math.asin(math.sqrt(a))


def _perp_dist_m(
    p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]
) -> float:
    """点到球面大圆段（小范围按平面近似）的垂直距离（米）。"""
    lat0, lon0 = p
    lat1, lon1 = a
    lat2, lon2 = b
    d_ab = haversine_m(lat1, lon1, lat2, lon2)
    if d_ab == 0:
        return haversine_m(lat1, lon1, lat0, lon0)
    d_a = haversine_m(lat1, lon1, lat0, lon0)
    d_b = haversine_m(lat2, lon2, lat0, lon0)
    proj = (d_a**2 - d_b**2 + d_ab**2) / (2 * d_ab)
    return math.sqrt(max(0.0, d_a**2 - proj**2))


def douglas_peucker(points: list[tuple[float, float]], eps_m: float) -> list[tuple[float, float]]:
    if len(points) <= 2:
        return list(points)
    dmax, idx = 0.0, 0
    for i in range(1, len(points) - 1):
        d = _perp_dist_m(points[i], points[0], points[-1])
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps_m:
        left = douglas_peucker(points[: idx + 1], eps_m)
        right = douglas_peucker(points[idx:], eps_m)
        return left[:-1] + right
    return [points[0], points[-1]]


def total_climb_m(elevations: list[float | None], threshold_m: float = 10.0) -> int:
    climb = 0.0
    last_ref: float | None = None
    for e in elevations:
        if e is None:
            continue
        if last_ref is None:
            last_ref = e
            continue
        if e - last_ref >= threshold_m:
            climb += e - last_ref
            last_ref = e
        elif e < last_ref:
            last_ref = e
    return round(climb)


def difficulty_from_stats(distance_km: float, climb_m: int) -> int:
    raw = 1 + climb_m / 800 + max(0.0, distance_km - 10) * 0.05
    return max(1, min(5, round(raw)))


def clarity_from_stats(points: int, distance_km: float) -> str:
    per_km = points / max(0.1, distance_km)
    if per_km >= 20:
        return "high"
    if per_km >= 5:
        return "mid"
    return "low"


def points_to_elevation_profile(points: list[tuple[float, float, float | None]]) -> list[dict]:
    prof: list[dict] = []
    dist_m = 0.0
    prev: tuple[float, float] | None = None
    for lat, lon, ele in points:
        if prev is not None:
            dist_m += haversine_m(prev[0], prev[1], lat, lon)
        prev = (lat, lon)
        if ele is not None:
            prof.append({"km": round(dist_m / 1000, 2), "m": round(ele)})
    return prof
