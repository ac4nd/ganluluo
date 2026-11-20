"""路线库种子：protype/route_guides.csv 每行 → 一条 Route（幂等：按 name 查重跳过）。

与既有手工种子（seed_routes.py 6 条）共存：CSV 含同名线（雨崩/虎跳峡等 5 条）则跳过，
保留手工行（track_points 演示数据不丢）。数字字段解析失败给安全默认并打 warning，
不中断导入（M8.7 计划全局约束）。
"""
import asyncio
import csv
import os
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.models.route import Route
from app.seeds.seed_kb import SPORT_MAP

# GL_ROUTES_CSV 可覆盖 CSV 路径；默认仓库原路径（同 seed_kb 的 GL_KB_CSV 惯例）
CSV_PATH = Path(os.environ.get("GL_ROUTES_CSV") or Path(__file__).resolve().parents[3] / "protype" / "route_guides.csv")

# CSV 运动类型多带括号备注（如「徒步（重装多日）」「骑行（城市绿道）」），精确匹配
# SPORT_MAP 失败后按前缀归类（覆盖 Sport 枚举其余值）；仍未命中默认 hiking（对齐 seed_kb）。
# 注意「徒步/越野跑」「定向越野」必须排在「徒步」「越野跑」之前做前缀判定。
SPORT_PREFIX_MAP: list[tuple[str, str]] = [
    ("徒步/越野跑", "trail-running"),
    ("定向越野", "orienteering"),
    ("越野跑", "trail-running"),
    ("徒步", "hiking"),
    ("骑行", "cycling"),
    ("露营", "camping"),
    ("滑雪", "skiing"),
    ("溯溪", "stream"),
    ("攀岩", "climbing"),
]

# 轨迹清晰度：CSV 值带长括号备注（如「高（全程指示牌+路迹明显…）」），按首字归类；其他 → mid
CLARITY_MAP = {"高": "high", "中": "mid", "低": "low"}

_FLOAT_RE = re.compile(r"\d+(?:\.\d+)?")
# 首个「Nh」口径；区间写法（"4.5-6h"）取区间首个数字（M8.7 计划 Self-Review 口径）
_HOURS_RE = re.compile(r"(\d+(?:\.\d+)?)(?:\s*[-–~]\s*\d+(?:\.\d+)?)?\s*[hH]")


def _first_float(text: str | None) -> float | None:
    """取文本中首个数字（整数或小数）；无数字返回 None。"""
    m = _FLOAT_RE.search(text or "")
    return float(m.group()) if m else None


def parse_sport(value: str) -> str:
    """运动类型 → Sport 枚举值：先精确匹配 seed_kb.SPORT_MAP，再前缀归类，兜底 hiking。"""
    if value in SPORT_MAP:
        return SPORT_MAP[value]
    for prefix, sport in SPORT_PREFIX_MAP:
        if value.startswith(prefix):
            return sport
    return "hiking"


def parse_clarity(value: str) -> str:
    """轨迹清晰度按首字归类：高→high 中→mid 低→low，其他（空/「体验段高」…）→ mid。"""
    return CLARITY_MAP.get((value or "")[:1], "mid")


def parse_difficulty(text: str) -> int:
    """难度首个数字四舍五入后 clamp 到 1-5；解析失败安全默认 1。"""
    v = _first_float(text)
    if v is None:
        return 1
    return max(1, min(5, round(v)))


def parse_hours(text: str) -> float | None:
    """建议用时首个「Nh」数字（区间"4.5-6h"取 4.5）；无小时口径返回 None（列可空）。"""
    m = _HOURS_RE.search(text or "")
    return float(m.group(1)) if m else None


def _trunc(text: str | None, limit: int) -> str | None:
    """截断到列宽上限（name/region 64、warning 255），None 透传。"""
    if text is None:
        return None
    return text[:limit]


def build_route(row: dict[str, str]) -> tuple[dict[str, object], list[str]]:
    """CSV 行 → Route 列字典 + 解析 warning 列表（不中断导入，调用方负责打印）。"""
    warnings: list[str] = []
    name = row.get("路线名称", "").strip()

    distance = _first_float(row.get("里程(km)"))
    if distance is None:
        distance = 0.0
        warnings.append("里程解析失败 → 0")
    climb = _first_float(row.get("累计爬升(m)"))
    if climb is None:
        climb = 0
        warnings.append("累计爬升解析失败 → 0")
    else:
        climb = round(climb)  # RouteOut.climb_m 为 int（首数字 "约1918.3m" → 1918；round(float) 即 int）
    difficulty = parse_difficulty(row.get("难度(1-5)") or "")
    if not _FLOAT_RE.search(row.get("难度(1-5)") or ""):
        warnings.append("难度解析失败 → 1")
    duration = parse_hours(row.get("建议用时") or "")
    if duration is None:
        warnings.append("建议用时无 Nh 口径 → None")

    terrain_text = (row.get("地形构成") or "").strip()
    data: dict[str, object] = {
        "name": _trunc(name, 64),
        "sport": parse_sport(row.get("运动类型", "")),
        "region": _trunc(row.get("所在地区") or "未标注地区", 64),
        "distance_km": distance,
        "climb_m": climb,
        "difficulty": difficulty,
        "duration_h": duration,
        "clarity": parse_clarity(row.get("轨迹清晰度") or ""),
        # 地形原文存单条占位（CSV 无结构化比例；pct=0 待后续结构化）
        "terrain": [{"type": terrain_text, "pct": 0}] if terrain_text else [],
        "elevation": [],
        "pace": [],
        "required_gear": [],
        "warning": _trunc(row.get("安全提醒") or None, 255),
        "status": "published",
        "source": "csv",
    }
    return data, warnings


def load_rows() -> list[dict[str, str]]:
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


async def seed_routes_csv(session: AsyncSession) -> dict[str, int]:
    """幂等导入：existing names 查询后跳过；返回统计（rows/added/skipped/warnings）。"""
    rows = await asyncio.to_thread(load_rows)
    existing = set((await session.execute(select(Route.name))).scalars())
    added = skipped = warn_total = 0
    for row in rows:
        name = (row.get("路线名称") or "").strip()[:64]
        if not name:
            continue
        if name in existing:
            skipped += 1
            continue
        data, warns = build_route(row)
        for w in warns:
            print(f"warning[{name}]: {w}")
        warn_total += len(warns)
        session.add(Route(**data))  # type: ignore[arg-type]
        existing.add(name)
        added += 1
    await session.commit()
    return {"rows": len(rows), "added": added, "skipped": skipped, "warnings": warn_total}


async def main() -> None:
    async with SessionLocal() as session:
        stats = await seed_routes_csv(session)
    print(f"csv rows: {stats['rows']}, added: {stats['added']}, "
          f"skipped(existing): {stats['skipped']}, parse warnings: {stats['warnings']}")


if __name__ == "__main__":
    asyncio.run(main())
