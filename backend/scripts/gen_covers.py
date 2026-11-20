"""轨迹封面批量生成：routes 表每条 → 确定性 SVG → 无头 Chrome 截 PNG。

产出 `backend/static/covers/{id}.png`（gitignore 生成产物；前端按 id 约定寻址，
加载失败回退页面内渐变模板）。设计（M8.7 计划）：
- 地貌渐变底：sport 5 组色板（森林/草甸/岩壁/溪谷/雪原，各 3 停渐变）
- 山脊剪影两层 + 日月圆
- 蜿蜒轨迹折线（accent #A4F150 发光，8-14 个拐点随机游走）
- 起点圆点 / 终点旗标
- 底部渐暗条 + 路线名（截 12 字）+ `Xkm ↑Ym ★N` 摘要行

确定性：随机源仅 `random.Random(route.id)`（种子=id），SVG 无时间戳 →
同 id 重跑逐字节一致。Chrome 截本地 file:// SVG，无外部网络请求。

用法（backend/ 下）：
    python scripts/gen_covers.py                # 全量
    python scripts/gen_covers.py --only 1,2,3   # 指定 id
    python scripts/gen_covers.py --limit 5      # 冒烟前 5 条
    python scripts/gen_covers.py --workers 4    # 并发 Chrome 进程数（默认 4）
"""
import argparse
import asyncio
import html
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.route import Route

BACKEND_DIR = Path(__file__).resolve().parent.parent
COVERS_DIR = BACKEND_DIR / "static" / "covers"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
W, H = 400, 240  # SVG viewBox（Chrome --window-size=430,258 同比例 5:3 全幅切片）
ACCENT = "#A4F150"

# sport → 地貌色板 5 组（顶/中/底三停）；未知 sport 兜底 forest
PALETTES: dict[str, tuple[str, str, str]] = {
    "forest": ("#41603a", "#26402a", "#0b140b"),   # hiking / trail-running / orienteering
    "meadow": ("#4a5a2c", "#2a3a18", "#0c1206"),   # camping / cycling
    "rock": ("#6a4a2a", "#33260f", "#0d0b06"),     # climbing
    "water": ("#2e6a5a", "#16332c", "#081210"),    # stream
    "snow": ("#3a5a72", "#22343a", "#0a1014"),     # skiing
}
SPORT_PALETTE = {
    "hiking": "forest", "trail-running": "forest", "orienteering": "forest",
    "camping": "meadow", "cycling": "meadow",
    "climbing": "rock",
    "stream": "water",
    "skiing": "snow",
}


@dataclass(frozen=True)
class CoverRoute:
    id: int
    name: str
    sport: str
    distance_km: float
    climb_m: int
    difficulty: int


def _mix(c1: str, c2: str, t: float) -> str:
    """两 hex 色线性插值（t=0 → c1，t=1 → c2）。"""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def _fmt_km(v: float) -> str:
    return f"{v:g}" if v else "0"


def _ridge(rng: random.Random, base: float, amp: float, fill: str) -> str:
    """山脊剪影一层：从左到右随机高度折线，闭合到底边。"""
    pts = ["M-10 " + f"{base + rng.uniform(-amp, amp * 0.6):.1f}"]
    x = -10.0
    while x < W + 10:
        x += rng.uniform(55, 105)
        pts.append(f"L{x:.1f} {base + rng.uniform(-amp, amp * 0.7):.1f}")
    pts.append(f"L{W + 10} {H} L-10 {H} Z")
    return f'<path d="{" ".join(pts)}" fill="{fill}"/>'


def _track(rng: random.Random) -> list[tuple[float, float]]:
    """蜿蜒轨迹 8-14 个拐点：从左下向右上随机游走（y 夹在山脊与底边之间）。"""
    n = rng.randint(8, 14)
    x, y = rng.uniform(30, 60), rng.uniform(160, 200)
    pts = [(x, y)]
    for _ in range(n - 1):
        x += rng.uniform(300 / (n - 1) * 0.55, 300 / (n - 1) * 1.45)
        y = max(86.0, min(206.0, y + rng.uniform(-36, 30)))
        pts.append((x, y))
    return pts


def build_svg(r: CoverRoute) -> str:
    rng = random.Random(r.id)
    pal = PALETTES[SPORT_PALETTE.get(r.sport, "forest")]
    ridge_far = _mix(pal[1], pal[0], 0.45)
    ridge_near = _mix(pal[2], "#000000", 0.18)
    pts = _track(rng)
    track = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    sx, sy = pts[0]
    ex, ey = pts[-1]
    name = html.escape(r.name[:12])
    summary = f"{_fmt_km(r.distance_km)}km ↑{r.climb_m}m ★{r.difficulty}"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid slice">
<defs>
<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="{pal[0]}"/><stop offset=".55" stop-color="{pal[1]}"/><stop offset="1" stop-color="{pal[2]}"/>
</linearGradient>
<linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="rgba(0,0,0,0)"/><stop offset="1" stop-color="rgba(0,0,0,.88)"/>
</linearGradient>
</defs>
<rect width="{W}" height="{H}" fill="url(#bg)"/>
<circle cx="{rng.uniform(40, 340):.0f}" cy="{rng.uniform(26, 60):.0f}" r="{rng.uniform(15, 26):.0f}" fill="#f2dd7d" opacity=".9"/>
{_ridge(rng, rng.uniform(92, 112), 30, ridge_far)}
{_ridge(rng, rng.uniform(136, 154), 24, ridge_near)}
<polyline points="{track}" fill="none" stroke="{ACCENT}" stroke-width="7" stroke-opacity=".22" stroke-linejoin="round" stroke-linecap="round"/>
<polyline points="{track}" fill="none" stroke="{ACCENT}" stroke-width="2.6" stroke-opacity=".95" stroke-linejoin="round" stroke-linecap="round"/>
<circle cx="{sx:.1f}" cy="{sy:.1f}" r="4.6" fill="#f6f9ef" stroke="#0d1506" stroke-width="1.5"/>
<path d="M{ex:.1f} {ey:.1f} v-20 l14 4.5 -14 4.5 z" fill="{ACCENT}"/>
<line x1="{ex:.1f}" y1="{ey:.1f}" x2="{ex:.1f}" y2="{ey - 20:.1f}" stroke="#f6f9ef" stroke-width="2"/>
<rect x="0" y="150" width="{W}" height="90" fill="url(#fade)"/>
<text x="24" y="204" font-size="21" font-weight="700" fill="#f4f7ef" stroke="rgba(0,0,0,.55)" stroke-width="3" paint-order="stroke" font-family="'Microsoft YaHei','PingFang SC',sans-serif">{name}</text>
<text x="24" y="226" font-size="12.5" fill="#c9d6b8" font-family="'Microsoft YaHei','PingFang SC',sans-serif">{summary}</text>
</svg>
"""


_local = threading.local()  # 每个 worker 线程独立 Chrome profile + svg 临时文件
_profiles: list[Path] = []  # 已建 profile 目录（结束统一清理）
_profiles_lock = threading.Lock()


def _worker_paths() -> tuple[Path, Path]:
    if not hasattr(_local, "profile"):
        _local.profile = Path(tempfile.mkdtemp(prefix="gl-chrome-"))
        _local.svg = _local.profile / "cover.svg"
        with _profiles_lock:
            _profiles.append(_local.profile)
    return _local.profile, _local.svg


def render_one(r: CoverRoute) -> tuple[int, str]:
    """SVG 写临时文件 → 无头 Chrome 截图 → {id}.png；返回 (id, 状态描述)。"""
    profile, svg_path = _worker_paths()
    png = COVERS_DIR / f"{r.id}.png"
    svg_path.write_text(build_svg(r), encoding="utf-8")
    cmd = [
        str(CHROME), "--headless=new", f"--screenshot={png.resolve()}",
        "--window-size=430,258",  # 与 viewBox 400x240 同比例 5:3，全幅切片无 letterbox
        "--hide-scrollbars", "--force-device-scale-factor=1",
        "--no-first-run", "--no-default-browser-check", "--disable-extensions",
        f"--user-data-dir={profile}", svg_path.as_uri(),
    ]
    proc = subprocess.run(cmd, capture_output=True, timeout=120, check=False)
    if proc.returncode != 0 or not png.exists() or png.stat().st_size == 0:
        err = (proc.stderr or proc.stdout or b"")[-200:].decode("utf-8", "replace")
        return r.id, f"chrome failed rc={proc.returncode}: {err}"
    return r.id, f"ok {png.stat().st_size // 1024}KB"


async def load_routes(only: Sequence[int] | None) -> list[CoverRoute]:
    async with SessionLocal() as session:
        stmt = select(Route.id, Route.name, Route.sport, Route.distance_km,
                      Route.climb_m, Route.difficulty).order_by(Route.id)
        if only:
            stmt = stmt.where(Route.id.in_(only))
        return [CoverRoute(*row) for row in (await session.execute(stmt)).all()]


def main() -> None:
    parser = argparse.ArgumentParser(description="生成路线轨迹封面 PNG")
    parser.add_argument("--workers", type=int, default=4, help="并发 Chrome 进程数（默认 4）")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 条（0=全量）")
    parser.add_argument("--only", type=str, default="", help="只处理指定 id，逗号分隔")
    args = parser.parse_args()

    only = [int(x) for x in args.only.split(",") if x.strip()] if args.only else None
    routes = asyncio.run(load_routes(only))
    if args.limit:
        routes = routes[:args.limit]
    if not routes:
        print("no routes to render")
        return
    COVERS_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.monotonic()
    failed: list[tuple[int, str]] = []
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for rid, status in pool.map(render_one, routes):
            done += 1
            if not status.startswith("ok"):
                failed.append((rid, status))
                print(f"[{done}/{len(routes)}] id={rid} {status}")
            elif done % 100 == 0 or done == len(routes):
                print(f"[{done}/{len(routes)}] latest id={rid} {status}")
    elapsed = time.monotonic() - t0

    # 清理本进程各 worker 的临时 profile 目录
    for profile in _profiles:
        shutil.rmtree(profile, ignore_errors=True)
    print(f"rendered: {len(routes) - len(failed)}/{len(routes)} ok, "
          f"failed: {len(failed)}, elapsed: {elapsed:.1f}s, out: {COVERS_DIR}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
