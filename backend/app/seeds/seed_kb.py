"""知识库种子：protype/route_guides.csv 每行 → 一篇攻略文档（幂等重建）。"""
import asyncio
import csv
import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.kb_service import ingest_document
from app.core.db import SessionLocal

# GL_KB_CSV 可覆盖 CSV 路径（远程集成容器内为 /app/route_guides.csv）；默认仓库原路径
CSV_PATH = Path(os.environ.get("GL_KB_CSV") or Path(__file__).resolve().parents[3] / "protype" / "route_guides.csv")

# 与 Sport 枚举对齐；未识别的运动类型默认 hiking
SPORT_MAP = {
    "徒步": "hiking",
    "徒步/越野跑": "trail-running",
    "骑行": "cycling",
    "露营": "camping",
    "滑雪": "skiing",
}


def build_text(row: dict[str, str]) -> str:
    """每列拼成 `字段名: 值` 行（跳过空值），换行连接。"""
    return "\n".join(f"{key}: {value}" for key, value in row.items() if str(value).strip())


def load_rows() -> list[dict[str, str]]:
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


async def seed_kb(session: AsyncSession) -> int:
    rows = await asyncio.to_thread(load_rows)
    total = 0
    for row in rows:
        name = row["路线名称"]
        n = await ingest_document(session, source_name=name, text=build_text(row),
                                  sport=SPORT_MAP.get(row.get("运动类型", ""), "hiking"),
                                  region=row.get("所在地区") or None)
        print(f"{name}: {n} chunks")
        total += n
    return total


async def main() -> None:
    async with SessionLocal() as session:
        print("total chunks:", await seed_kb(session))


if __name__ == "__main__":
    asyncio.run(main())
