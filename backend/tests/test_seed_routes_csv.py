"""M8.7 seed_routes_csv：CSV 数字/枚举解析边界 + 幂等两跑导入。"""
import csv

from sqlalchemy import select

from app.models.route import Route
from app.seeds import seed_routes_csv
from app.seeds.seed_routes_csv import (
    _first_float,
    build_route,
    parse_clarity,
    parse_difficulty,
    parse_hours,
    parse_sport,
)

HEADER = ["路线名称", "运动类型", "所在地区", "里程(km)", "累计爬升(m)", "难度(1-5)",
          "建议用时", "轨迹清晰度", "地形构成", "安全提醒"]


def write_csv(path, rows: list[dict[str, str]]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def row(**over: str) -> dict[str, str]:
    base = {
        "路线名称": "测试线（甲山→乙山）",
        "运动类型": "徒步",
        "所在地区": "浙江杭州·测试山脉",
        "里程(km)": "约12.5km（往返）",
        "累计爬升(m)": "800-941m",
        "难度(1-5)": "2.5/5（入门线）",
        "建议用时": "神瀑线4.5-6h；冰湖线6-7h",
        "轨迹清晰度": "高（全程指示牌+路迹明显）",
        "地形构成": "铺装台阶/石板路",
        "安全提醒": "雨天路滑",
    }
    base.update(over)
    return base


# ---------- 解析边界 ----------

def test_first_float_takes_first_number():
    assert _first_float("村内两日线往返约26.7km（神瀑12km+冰湖14km）") == 26.7
    assert _first_float("约3900m（冰湖）") == 3900.0
    assert _first_float("环线约54km/8天") == 54.0
    assert _first_float("") is None
    assert _first_float(None) is None
    assert _first_float("组别以现场公布为准") is None


def test_parse_difficulty_round_and_clamp():
    assert parse_difficulty("2.5/5（高原入门线·含高反风险）") == 2
    assert parse_difficulty("2/5（精华段）；3/5（高路全程）") == 2
    assert parse_difficulty("9/5（超界）") == 5  # clamp 上界
    assert parse_difficulty("0.4（超界）") == 1  # clamp 下界
    assert parse_difficulty("") == 1  # 解析失败安全默认
    assert parse_difficulty("高（无数字）") == 1


def test_parse_clarity_by_first_char():
    assert parse_clarity("高（全程指示牌+路迹明显·两步路轨迹量大）") == "high"
    assert parse_clarity("中（山脊主路明显但岔路多）") == "mid"
    assert parse_clarity("低-中（野路为主·极易迷路）") == "low"
    assert parse_clarity("体验段高（景区绿道）") == "mid"  # 非高/中/低开头 → mid
    assert parse_clarity("") == "mid"


def test_parse_hours_first_nh():
    assert parse_hours("神瀑线4.5-6h；冰湖线6-7h") == 4.5
    assert parse_hours("5-6h（含拍照）") == 5.0
    assert parse_hours("精华3天2夜") is None  # 无 Nh 口径 → None
    assert parse_hours("") is None


def test_parse_sport_exact_prefix_default():
    assert parse_sport("徒步") == "hiking"
    assert parse_sport("徒步（重装多日·小众秘境）") == "hiking"  # 前缀
    assert parse_sport("徒步/越野跑") == "trail-running"  # 精确
    assert parse_sport("越野跑") == "trail-running"
    assert parse_sport("定向越野（城市定向）") == "orienteering"
    assert parse_sport("骑行（城市环岛绿道·亲子休闲线）") == "cycling"
    assert parse_sport("滑雪（高山滑雪·西北最大）") == "skiing"
    assert parse_sport("溯溪（火山岩峡谷）") == "stream"
    assert parse_sport("攀岩（运动攀为主）") == "climbing"
    assert parse_sport("翼装飞行") == "hiking"  # 未识别默认 hiking


# ---------- build_route 列映射 ----------

def test_build_route_column_mapping():
    data, warns = build_route(row())
    assert warns == []
    assert data["name"] == "测试线（甲山→乙山）"
    assert data["sport"] == "hiking"
    assert data["region"] == "浙江杭州·测试山脉"
    assert data["distance_km"] == 12.5
    assert data["climb_m"] == 800
    assert isinstance(data["climb_m"], int)  # RouteOut.climb_m: int（小数爬升要取整）
    assert data["difficulty"] == 2  # 2.5 → round → 2
    assert data["duration_h"] == 4.5
    assert data["clarity"] == "high"
    assert data["terrain"] == [{"type": "铺装台阶/石板路", "pct": 0}]
    assert data["warning"] == "雨天路滑"
    assert data["elevation"] == [] and data["pace"] == [] and data["required_gear"] == []
    assert data["status"] == "published"
    assert data["source"] == "csv"

    # 小数爬升取整（RouteOut.climb_m: int，否则列表序列化 500）
    frac, _ = build_route(row(**{"累计爬升(m)": "约1918.3m"}))
    assert frac["climb_m"] == 1918


def test_build_route_safe_defaults_and_truncation():
    long_name = "超" * 80
    data, warns = build_route(row(**{
        "路线名称": long_name,
        "里程(km)": "组别以现场公布为准",
        "累计爬升(m)": "",
        "难度(1-5)": "未知",
        "建议用时": "体验段半天",
        "轨迹清晰度": "好（县城补给）",
        "地形构成": "",
    }))
    assert data["name"] == "超" * 64  # name 列 String(64)
    assert data["distance_km"] == 0.0
    assert data["climb_m"] == 0
    assert data["difficulty"] == 1
    assert data["duration_h"] is None
    assert data["clarity"] == "mid"
    assert data["terrain"] == []
    assert len(warns) == 4  # 里程/爬升/难度/用时各一条 warning


# ---------- 幂等两跑导入（含同名手工种子跳过） ----------

async def test_seed_idempotent_two_runs(db, tmp_path, monkeypatch):
    # 预置一条「手工种子」同名线（模拟 seed_routes 的雨崩/虎跳峡场景）
    db.add(Route(name="武功山反穿（龙山村→金顶）", region="江西萍乡", sport="hiking", distance_km=25.0))
    await db.commit()

    csv_file = tmp_path / "routes.csv"
    write_csv(csv_file, [
        row(路线名称="武功山反穿（龙山村→金顶）"),  # 与手工种子同名 → 跳过
        row(路线名称="新线一（测试）"),
        row(路线名称="新线二（测试）", 运动类型="骑行（城市绿道）"),
    ])
    monkeypatch.setattr(seed_routes_csv, "CSV_PATH", csv_file)

    first = await seed_routes_csv.seed_routes_csv(db)
    assert first == {"rows": 3, "added": 2, "skipped": 1, "warnings": 0}

    second = await seed_routes_csv.seed_routes_csv(db)
    assert second == {"rows": 3, "added": 0, "skipped": 3, "warnings": 0}

    names = set((await db.execute(select(Route.name))).scalars())
    assert names == {"武功山反穿（龙山村→金顶）", "新线一（测试）", "新线二（测试）"}
