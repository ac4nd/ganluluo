import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.models.route import Route

ROUTES = [
    {
        "name": "雨崩徒步（神瀑+冰湖精华线）", "region": "云南迪庆州德钦县·梅里雪山",
        "sport": "hiking", "difficulty": 3, "distance_km": 26.7, "climb_m": 941,
        "duration_h": 18.0, "clarity": "high",
        "terrain": [{"type": "铺装台阶/石板", "pct": 40}, {"type": "原始森林野路", "pct": 30}, {"type": "溪流碎石", "pct": 20}, {"type": "峡谷土路", "pct": 10}],
        "elevation": [{"km": 0.0, "m": 3450}, {"km": 1.2, "m": 2600}, {"km": 3.4, "m": 3200}, {"km": 6.0, "m": 3650}, {"km": 9.0, "m": 3900}, {"km": 12.0, "m": 3050}],
        "pace": [], "required_gear": ["rain-gear", "midlayer", "boots", "first-aid"],
        "warning": "平均海拔 3300m 有高反风险；冰湖线入口需签风险告知书；勿摸黑下山",
        "start_lat": 28.35, "start_lon": 98.88, "source": "guide",
    },
    {
        "name": "虎跳峡高路徒步（一日精华段）", "region": "云南迪庆州香格里拉市 ⇄ 丽江",
        "sport": "hiking", "difficulty": 2, "distance_km": 10.0, "climb_m": 650,
        "duration_h": 5.5, "clarity": "high",
        "terrain": [{"type": "平缓土路/村道", "pct": 33}, {"type": "悬崖碎石路", "pct": 47}, {"type": "大石头陡坡", "pct": 20}],
        "elevation": [{"km": 0.0, "m": 2600}, {"km": 2.0, "m": 2650}, {"km": 4.5, "m": 2400}, {"km": 8.0, "m": 1950}],
        "pace": [], "required_gear": ["boots", "sunscreen", "rain-gear"],
        "warning": "走路不拍照拍照不走路；阴雨天不要走；龙洞瀑布段水雾大路滑",
        "start_lat": 27.28, "start_lon": 100.08, "source": "guide",
    },
    {
        "name": "五台山顺朝（三天两夜大朝台）", "region": "山西忻州市五台县",
        "sport": "hiking", "difficulty": 4, "distance_km": 75.0, "climb_m": 3400,
        "duration_h": 21.0, "clarity": "high",
        "terrain": [{"type": "高山草甸", "pct": 60}, {"type": "石台阶", "pct": 25}, {"type": "土路", "pct": 15}],
        "elevation": [], "pace": [], "required_gear": ["boots", "midlayer", "rain-gear", "headlamp", "first-aid"],
        "warning": "长距离持续爬升；山顶风大温低；补给与下撤点充足",
        "start_lat": 38.99, "start_lon": 113.53, "source": "guide",
    },
    {
        "name": "南太行穿越（双底/马武寨→韩口）", "region": "河南新乡辉县 ⇄ 山西陵川",
        "sport": "hiking", "difficulty": 4, "distance_km": 45.0, "climb_m": 1800,
        "duration_h": 20.0, "clarity": "mid",
        "terrain": [{"type": "山脊土路", "pct": 45}, {"type": "悬崖路段", "pct": 25}, {"type": "峡谷碎石", "pct": 30}],
        "elevation": [], "pace": [], "required_gear": ["boots", "poles", "headlamp", "first-aid"],
        "warning": "悬崖路段+绝望坡，新手勿单独走；岔路多，必须下载离线轨迹",
        "start_lat": 35.62, "start_lon": 113.42, "source": "guide",
    },
    {
        "name": "武功山反穿（龙山村→金顶）", "region": "江西萍乡市·罗霄山脉北支",
        "sport": "hiking", "difficulty": 3, "distance_km": 25.0, "climb_m": 2245,
        "duration_h": 8.0, "clarity": "high",
        "terrain": [{"type": "高山草甸", "pct": 55}, {"type": "台阶与土路", "pct": 35}, {"type": "碎石", "pct": 10}],
        "elevation": [{"km": 0.0, "m": 480}, {"km": 6.0, "m": 1300}, {"km": 12.0, "m": 1900}, {"km": 18.0, "m": 1918}],
        "pace": [], "required_gear": ["boots", "poles", "sun-cap", "rain-gear"],
        "warning": "一日连穿强度大；山顶露营注意防风保暖",
        "start_lat": 27.45, "start_lon": 114.13, "source": "guide",
    },
    {
        "name": "徽杭古道 · 经典穿越", "region": "安徽绩溪 ⇄ 浙江永来",
        "sport": "hiking", "difficulty": 3, "distance_km": 16.8, "climb_m": 950,
        "duration_h": 6.0, "clarity": "high",
        "terrain": [{"type": "青石阶/石板路", "pct": 45}, {"type": "山林土路", "pct": 30}, {"type": "碎石坡", "pct": 15}, {"type": "木栈道", "pct": 10}],
        "elevation": [{"km": 0.0, "m": 420}, {"km": 4.0, "m": 680}, {"km": 9.5, "m": 1180}, {"km": 12.5, "m": 900}, {"km": 16.8, "m": 620}],
        "pace": [{"km": 0.0, "pace": 12}, {"km": 4.0, "pace": 14}, {"km": 9.5, "pace": 15}, {"km": 10.5, "pace": 9}, {"km": 14.0, "pace": 10}, {"km": 16.8, "pace": 10}],
        "required_gear": ["boots", "backpack", "shell", "headlamp", "first-aid"],
        "warning": "垭口午后风大；沿线信号弱，建议离线轨迹结伴同行",
        "start_lat": 30.12, "start_lon": 118.82, "source": "seed",
    },
]


async def seed_routes(session: AsyncSession) -> int:
    added = 0
    for data in ROUTES:
        exists = (await session.execute(
            select(Route).where(Route.name == data["name"])
        )).scalar_one_or_none()
        if exists is None:
            session.add(Route(**data))
            added += 1
    await session.commit()
    return added


async def main() -> None:
    async with SessionLocal() as session:
        print("seeded routes:", await seed_routes(session))


if __name__ == "__main__":
    asyncio.run(main())
