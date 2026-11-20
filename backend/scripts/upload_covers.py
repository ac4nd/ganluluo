"""路线封面图批量上传 MinIO（M8.8-covers-minio）。

protype/covers/*.jpg（`NNNN_路线名.jpg`，用户提供 1470 张 = CSV 1470 行）匹配 routes 表两级：
1. 路线名双向包含（`file_name[:10] in name or name in file_name`）且**唯一命中**；
2. 兜底：序号即 CSV 行号（brief 资源事实）→ csv_names[N] 与 file_name 相关性校验后
   按 CSV 行名与 routes.name **精确相等**唯一命中（解决同名变体路线的多候选歧义）。
两级都未命中 → unmatched 清单打印（人工兜底）。上传 `covers/{id}.jpg` 并回写
`routes.cover_url`。

- MinIO 走 GL_MINIO_* env（本脚本强依赖，缺配置 SystemExit 报错退出）；
  bucket 自动 ensure_bucket + covers/ 前缀匿名只读 policy（s3:GetObject）。
- 断点续传：cover_url 已等于本次将写入的 URL → 跳过（put_object 同 key 覆盖幂等，
  重跑安全）。commit 每 50 条一批。
- --limit N 只处理前 N 个文件（冒烟）；--dry-run 只匹配不上传不写库。

用法（backend/ 下，先 unset 代理让 SDK 直连 MinIO）：
    python scripts/upload_covers.py --dry-run          # 只看匹配结果
    python scripts/upload_covers.py --limit 3          # 冒烟 3 张
    python scripts/upload_covers.py                    # 全量（1476 张约 476MB）
"""
import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.db import SessionLocal
from app.models.route import Route
from app.seeds.seed_routes_csv import load_rows

REPO_DIR = Path(__file__).resolve().parents[2]
DEFAULT_COVERS_DIR = REPO_DIR / "protype" / "covers"

# `NNNN_路线名.jpg`：4 位序号 + 路线名（序号即 CSV 行号，匹配只用名字部分）
COVER_RE = re.compile(r"^(\d{4})_(.+)\.jpg$")
CONTENT_TYPE = "image/jpeg"
BATCH_COMMIT = 50
PROGRESS_EVERY = 20

# 匹配截断长度：file_name 前 10 字作前缀包含探测（M8.8 计划口径）
PREFIX_LEN = 10


class CoverUploader(Protocol):
    """run_upload 依赖的最小上传面（MinioMediaStore 结构化满足；测试用 Fake）。"""

    async def put_object(self, key: str, data: bytes, content_type: str) -> None: ...


@dataclass
class UploadStats:
    scanned: int = 0
    matched: int = 0
    uploaded: int = 0
    resumed: int = 0
    unmatched: int = 0
    unmatched_files: list[str] = field(default_factory=list)


def match_route(file_name: str, routes: list[tuple[int, str]]) -> int | None:
    """路线名双向包含唯一命中 → route id；0 或多个候选 → None（进 unmatched 清单）。

    - `file_name[:10] in name`：文件名截断差异（CSV name 可能比文件名长/短）
    - `name in file_name`：文件名比 DB name 长（括号备注被截）时反向包含
    """
    prefix = file_name[:PREFIX_LEN]
    hits = [rid for rid, name in routes if name and (prefix in name or name in file_name)]
    return hits[0] if len(hits) == 1 else None


def _related(a: str, b: str) -> bool:
    """双向包含相关性（同 match_route 口径），seq 兜底匹配前校验文件名与 CSV 行名同源。"""
    return bool(a) and bool(b) and (a[:PREFIX_LEN] in b or b in a)


def csv_names_by_seq(rows: list[dict[str, str]]) -> dict[int, str]:
    """covers 序号即 CSV 行号（brief 资源事实）→ seq(1 起) → 该行路线名称（截 64 同 DB 口径）。"""
    return {i: ((r.get("路线名称") or "").strip())[:64] for i, r in enumerate(rows, 1)}


def collect_covers(covers_dir: Path) -> list[tuple[int, str, Path]]:
    """目录 → [(序号, 名字部分, 路径)]，仅取匹配 `NNNN_*.jpg` 的文件；按文件名排序（稳定）。"""
    out: list[tuple[int, str, Path]] = []
    for p in sorted(covers_dir.glob("*.jpg")):
        m = COVER_RE.match(p.name)
        if m:
            out.append((int(m.group(1)), m.group(2), p))
    return out


async def run_upload(
    session: AsyncSession,
    store: CoverUploader,
    covers_dir: Path,
    base_url: str,
    limit: int | None = None,
    dry_run: bool = False,
    csv_names: dict[int, str] | None = None,
) -> UploadStats:
    """匹配 + 上传 + 回写 cover_url 的核心流程（store/session 注入，可测）。

    dry_run=True 只匹配不写不传；unmatched 文件名进 stats.unmatched_files（人工兜底清单）。
    """
    covers = collect_covers(covers_dir)
    if limit is not None:
        covers = covers[:limit]
    rows = (await session.execute(select(Route.id, Route.name, Route.cover_url))).all()
    routes: list[tuple[int, str]] = [(rid, name) for rid, name, _ in rows]
    url_by_id: dict[int, str | None] = {rid: cover for rid, _, cover in rows}

    stats = UploadStats(scanned=len(covers))
    pending = 0  # 本批待 commit 的写库数
    total = len(covers)
    for i, (seq, file_name, path) in enumerate(covers, 1):
        rid = match_route(file_name, routes)
        if rid is None and csv_names:
            # 兜底：序号 → CSV 行名（相关性校验防错位）→ 精确相等唯一命中
            csv_name = csv_names.get(seq, "")
            if _related(file_name, csv_name):
                exact = [r_id for r_id, r_name in routes if r_name == csv_name]
                rid = exact[0] if len(exact) == 1 else None
        if rid is None:
            stats.unmatched += 1
            stats.unmatched_files.append(path.name)
            continue
        stats.matched += 1
        key = f"covers/{rid}.jpg"
        cover_url = f"{base_url}/{key}"
        if url_by_id.get(rid) == cover_url:
            # 断点续传：对象已上传且库里 URL 已对 → 跳过
            stats.resumed += 1
            continue
        if dry_run:
            continue
        data = await asyncio.to_thread(path.read_bytes)
        await store.put_object(key, data, CONTENT_TYPE)
        stats.uploaded += 1
        await session.execute(update(Route).where(Route.id == rid).values(cover_url=cover_url))
        pending += 1
        if pending % BATCH_COMMIT == 0:
            await session.commit()
        if i % PROGRESS_EVERY == 0 or i == total:
            print(f"[{i}/{total}] uploaded={stats.uploaded} resumed={stats.resumed} "
                  f"unmatched={stats.unmatched}")
    if not dry_run:
        await session.commit()
    return stats


def print_stats(stats: UploadStats) -> None:
    print("\n=== covers upload stats ===")
    print(f"scanned: {stats.scanned}  matched: {stats.matched}  uploaded: {stats.uploaded}  "
          f"resumed(cover_url ok): {stats.resumed}  unmatched: {stats.unmatched}")
    if stats.unmatched_files:
        print("unmatched files（人工兜底：核对文件名与 routes.name 差异）:")
        for n in stats.unmatched_files:
            print(f"  - {n}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="路线封面图上传 MinIO（M8.8）")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 个文件（冒烟）")
    parser.add_argument("--dry-run", action="store_true", help="只匹配不上传不写库")
    parser.add_argument("--covers-dir", type=str, default=None, help="封面目录（默认 protype/covers）")
    args = parser.parse_args()

    # minio SDK 走 urllib3 PoolManager 直连，环境代理（Clash 等）会拦公网 IP——
    # 本脚本一律清掉代理 env（brief 环境坑）
    for k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        os.environ.pop(k, None)

    endpoint = os.environ.get("GL_MINIO_ENDPOINT", "").strip()
    access_key = os.environ.get("GL_MINIO_ACCESS_KEY", "").strip()
    secret_key = os.environ.get("GL_MINIO_SECRET_KEY", "").strip()
    bucket = os.environ.get("GL_MINIO_BUCKET", "").strip()
    missing = [k for k, v in (("GL_MINIO_ENDPOINT", endpoint), ("GL_MINIO_ACCESS_KEY", access_key),
                              ("GL_MINIO_SECRET_KEY", secret_key), ("GL_MINIO_BUCKET", bucket)) if not v]
    if missing:
        raise SystemExit(f"缺少 MinIO 配置 env：{', '.join(missing)}（本脚本强依赖 MinIO）")
    secure = os.environ.get("GL_MINIO_SECURE", "").strip().lower() == "true"
    base_url = f"{'https' if secure else 'http'}://{endpoint}/{bucket}"

    # media 域抽象复用：MinioMediaStore（ensure_bucket 内部 to_thread，I-6 模式）。
    # dry-run 只做本地匹配校验：不 ensure_bucket/不设 policy/零网络 IO（构造是纯本地）。
    from app.domains.media.media_store import MinioMediaStore

    store = MinioMediaStore(endpoint, access_key, secret_key, bucket, secure=secure)
    if not args.dry_run:
        await store.ensure_bucket()
        # covers/ 前缀匿名只读（media 私有区不受影响）：minio SDK set_bucket_policy
        policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket}/covers/*"],
            }],
        }
        await asyncio.to_thread(store._client.set_bucket_policy, bucket, json.dumps(policy))

    covers_dir = Path(args.covers_dir) if args.covers_dir else DEFAULT_COVERS_DIR
    mode = "dry-run（只匹配不上传）" if args.dry_run else "upload"
    print(f"covers dir: {covers_dir}  base_url: {base_url}  mode: {mode}")
    async with SessionLocal() as session:
        csv_rows = await asyncio.to_thread(load_rows)
        stats = await run_upload(session, store, covers_dir, base_url,
                                 limit=args.limit, dry_run=args.dry_run,
                                 csv_names=csv_names_by_seq(csv_rows))
    print_stats(stats)
    if stats.unmatched:
        sys.exit(2)  # 有未匹配文件：退出码非 0 提示人工兜底（上传/更新本身已成功）


if __name__ == "__main__":
    asyncio.run(main())
