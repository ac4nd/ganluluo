from app.domains.sports.geo import (
    clarity_from_stats,
    difficulty_from_stats,
    douglas_peucker,
    haversine_m,
    points_to_elevation_profile,
    total_climb_m,
)


def test_haversine_known_distance():
    # 北京天安门 -> 上海人民广场 约 1067km
    d = haversine_m(39.9087, 116.3975, 31.2304, 121.4737)
    assert 1_050_000 < d < 1_090_000


def test_douglas_peucker_keeps_endpoints_and_corners():
    pts = [(0.0, 0.0), (0.001, 0.05), (0.002, 0.0)]  # 中间点明显偏离
    out = douglas_peucker(pts, eps_m=5)
    assert out[0] == pts[0] and out[-1] == pts[-1]
    assert len(out) == 3


def test_douglas_peucker_collinear_collapse():
    pts = [(0.0, 0.0), (0.001, 0.0), (0.002, 0.0), (0.003, 0.0)]
    out = douglas_peucker(pts, eps_m=50)
    assert len(out) == 2


def test_total_climb_threshold():
    assert total_climb_m([100, 108, 106, 118, 130], threshold_m=10) == 30
    assert total_climb_m([100, 105, 103], threshold_m=10) == 0


def test_difficulty_bands():
    assert difficulty_from_stats(5, 200) == 1
    assert difficulty_from_stats(16.8, 950) == 3
    assert difficulty_from_stats(70, 3400) == 5
    assert 1 <= difficulty_from_stats(11.2, 780) <= 5


def test_clarity_bands():
    assert clarity_from_stats(400, 16.8) == "high"
    assert clarity_from_stats(120, 16.8) == "mid"
    assert clarity_from_stats(30, 16.8) == "low"


def test_elevation_profile_units():
    pts = [(0.0, 0.0, 420.0), (0.01, 0.01, 520.0), (0.03, 0.03, 380.0)]
    prof = points_to_elevation_profile(pts)
    assert prof[0] == {"km": 0.0, "m": 420}
    assert prof[-1]["m"] == 380
    assert all(set(p) == {"km", "m"} for p in prof)
