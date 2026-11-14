"""远程 PG 集成验证：docker SDK → 上传后端源码 → 迁移 + 种子 + 冒烟检查。

流程（对 GL_DOCKER_HOST 指定的远程 docker daemon 执行，本机不直连 PG）：
1. 打包 backend/ 源码（app/ alembic/ scripts/ tests/ pyproject.toml alembic.ini
   + protype/route_guides.csv → /app/route_guides.csv）tar 上传（put_archive）；
2. 确保 ganluluo-net 网络存在并接入 ganluluo-pg；
3. 起一次性容器 ganluluo-integration（python:3.12-slim，不映射端口）；
4. 容器内：pip 装依赖（阿里云镜像）→ alembic upgrade head → 三个种子 → 冒烟查询；
5. 打印 PASS/FAIL 汇总；finally 恒删容器。

注意：docker SDK 走 2375 端口，脚本启动时自动 unset 本机代理环境变量。
"""
import io
import os
import sys
import tarfile
from pathlib import Path

# docker SDK 底层 requests 会读取代理环境变量，直连 2375 前必须清掉
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy",
           "all_proxy", "NO_PROXY", "no_proxy"):
    os.environ.pop(_k, None)

from docker import DockerClient
from docker.errors import APIError, NotFound

DOCKER_HOST = os.environ.get("GL_DOCKER_HOST")
PG_URL = os.environ.get("GL_PG_URL", "")
NETWORK = "ganluluo-net"
PG_CONTAINER = "ganluluo-pg"
INTEGRATION = "ganluluo-integration"
PIP_MIRROR = "https://mirrors.aliyun.com/pypi/simple/"

BACKEND = Path(__file__).resolve().parents[1]
CSV_SRC = BACKEND.parent / "protype" / "route_guides.csv"

SMOKE = f"""
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

URL = "{PG_URL}"

async def main():
    engine = create_async_engine(URL)
    async with engine.connect() as c:
        gear = (await c.execute(text("select count(*) from gear_models"))).scalar()
        routes = (await c.execute(text("select count(*) from routes"))).scalar()
        docs = (await c.execute(text("select count(*) from kb_docs"))).scalar()
        chunks = (await c.execute(text("select count(*) from kb_chunks"))).scalar()
        emb = (await c.execute(text(
            "select format_type(a.atttypid, a.atttypmod) from pg_attribute a"
            " join pg_class cl on cl.oid = a.attrelid"
            " where cl.relname='kb_chunks' and a.attname='embedding'"))).scalar()
        start_pt = (await c.execute(text(
            "select format_type(a.atttypid, a.atttypmod) from pg_attribute a"
            " join pg_class cl on cl.oid = a.attrelid"
            " where cl.relname='routes' and a.attname='start_pt'"))).scalar()
        hnsw = (await c.execute(text(
            "select count(*) from pg_indexes where indexname='idx_chunks_hnsw'"
            " and schemaname='public'"))).scalar()
        # 混合检索冒烟：FakeEmbedder 与种子一致（确定性），取向量最近邻一条
        import sys; sys.path.insert(0, "/app")
        from app.assistant.embedder import FakeEmbedder
        q = "[" + ",".join(f"{{v:.6f}}" for v in FakeEmbedder().embed(["雨崩徒步"])[0]) + "]"
        hit = (await c.execute(text(
            "select coalesce(sport, ''), left(content, 24), 1 - (embedding <=> CAST(:q AS vector))"
            " from kb_chunks order by embedding <=> CAST(:q AS vector) limit 1"),
            {{"q": q}})).first()
        # M4-M5 迁移覆盖：0010 trips / 0011 route_tracks / 0012 admin flags / 0013 quota
        ver = (await c.execute(text("select version_num from alembic_version"))).scalar()
        trip_tbl = (await c.execute(text(
            "select count(*) from information_schema.tables"
            " where table_name='trip_plans' and table_schema='public'"))).scalar()
        track_tbl = (await c.execute(text(
            "select count(*) from information_schema.tables"
            " where table_name='route_tracks' and table_schema='public'"))).scalar()
        agent_tbl = (await c.execute(text(
            "select count(*) from information_schema.tables t where t.table_name in"
            " ('assistant_sessions','assistant_messages') and t.table_schema='public'"))).scalar()
        user_cols = (await c.execute(text(
            "select count(*) from information_schema.columns where table_name='users'"
            " and column_name in ('is_admin','disabled','quota_tier')"))).scalar()
        quota_tbls = (await c.execute(text(
            "select count(*) from information_schema.tables t where t.table_name in"
            " ('quota_tiers','llm_usage','sub_tokens') and t.table_schema='public'"))).scalar()
    await engine.dispose()
    checks = [
        ("gear_models == 116", gear == 116, gear),
        ("routes == 6", routes == 6, routes),
        ("kb_docs >= 5", docs >= 5, docs),
        ("kb_chunks > 0", chunks > 0, chunks),
        ("kb_chunks.embedding is vector(1024)", emb == "vector(1024)", emb),
        ("routes.start_pt is geography(Point,4326)", start_pt == "geography(Point,4326)", start_pt),
        ("HNSW index idx_chunks_hnsw exists", hnsw == 1, hnsw),
        ("vector NN smoke hit", hit is not None and hit[2] > 0, hit),
        ("alembic version == 0013", ver == "0013", ver),
        ("trip_plans table exists (0010)", trip_tbl == 1, trip_tbl),
        ("route_tracks table exists (0011)", track_tbl == 1, track_tbl),
        ("assistant_* tables renamed back (0007/0008)", agent_tbl == 2, agent_tbl),
        ("users is_admin/disabled/quota_tier columns (0012/0013)", user_cols == 3, user_cols),
        ("quota_tiers/llm_usage/sub_tokens tables (0013)", quota_tbls == 3, quota_tbls),
    ]
    print("smoke rows:", dict(gear=gear, routes=routes, docs=docs, chunks=chunks,
                              embedding=emb, start_pt=start_pt, hnsw=hnsw, nn=hit,
                              ver=ver, trips=trip_tbl, tracks=track_tbl,
                              agent_tbls=agent_tbl, user_cols=user_cols,
                              quota_tbls=quota_tbls))
    failed = [name for name, ok, _ in checks if not ok]
    for name, ok, val in checks:
        print(("PASS" if ok else "FAIL"), name, "->", val)
    raise SystemExit(1 if failed else 0)

asyncio.run(main())
"""


def build_tar() -> bytes:
    """backend 源码 + CSV → 内存 tar（排除 __pycache__）。"""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for folder in ("app", "alembic", "scripts", "tests"):
            base = BACKEND / folder
            for p in sorted(base.rglob("*")):
                if p.is_file() and "__pycache__" not in p.parts:
                    tf.add(p, arcname=f"{folder}/{p.relative_to(base).as_posix()}", recursive=False)
        for fname in ("pyproject.toml", "alembic.ini"):
            tf.add(BACKEND / fname, arcname=fname)
        tf.add(CSV_SRC, arcname="route_guides.csv")
    return buf.getvalue()


def check_host_disk(client: DockerClient) -> None:
    """宿主机根盘剩余 < 2GiB 时直接失败：满盘会让 PG 写入报错甚至拖死 docker daemon。"""
    ctr = client.containers.create(
        "alpine:3.20", ["sh", "-c", "df -m /host | tail -1"],  # busybox df：$4=可用 MiB
        volumes={"/": {"bind": "/host", "mode": "ro"}}, name="gl-df-check")
    try:
        ctr.start()
        ctr.wait(timeout=60)
        line = ctr.logs().decode().strip().splitlines()[-1]
        avail_mib = int(line.split()[3])
    finally:
        ctr.remove(force=True)
    print(f"[0] host root fs free: {avail_mib} MiB")
    if avail_mib < 2048:
        raise SystemExit("FAIL: 宿主机根盘剩余空间不足 2GiB，请先清理后再跑集成验证")


def main() -> int:
    if not DOCKER_HOST or not PG_URL:
        raise SystemExit("需要 GL_DOCKER_HOST 与 GL_PG_URL 环境变量（见 .env.example）")
    client = DockerClient(base_url=DOCKER_HOST)
    print(f"[0] docker ping: {client.ping()} ({DOCKER_HOST})")
    check_host_disk(client)

    try:
        net = client.networks.get(NETWORK)
    except NotFound:
        net = client.networks.create(NETWORK, driver="bridge")
    print(f"[1] network {NETWORK}: id={net.short_id}")
    try:
        net.connect(PG_CONTAINER)
        print(f"[1] connected {PG_CONTAINER} -> {NETWORK}")
    except APIError as e:  # 已接入会抛 403/409
        print(f"[1] {PG_CONTAINER} already on {NETWORK} ({e.response.status_code})")

    try:  # 清理同名旧容器
        client.containers.get(INTEGRATION).remove(force=True)
        print(f"[2] removed stale {INTEGRATION}")
    except NotFound:
        pass

    ctr = client.containers.run("python:3.12-slim", "sleep infinity", detach=True,
                                name=INTEGRATION, network=NETWORK,
                                working_dir="/app")
    print(f"[2] container {INTEGRATION} up ({ctr.short_id})")
    results: list[tuple[str, bool]] = []
    try:
        payload = build_tar()
        ok = ctr.put_archive("/app", payload)
        print(f"[3] put_archive /app: {ok} ({len(payload) / 1024:.0f} KiB)")
        results.append(("put_archive", ok))

        steps: list[tuple[str, str]] = [
            ("pip install -e /app",
             f"pip install -i {PIP_MIRROR} -e /app --no-deps"),
            ("pip install deps",
             (f"pip install -i {PIP_MIRROR} 'sqlalchemy[asyncio]' asyncpg alembic"
              " pydantic-settings pwdlib email-validator gpxpy pgvector httpx slowapi"
              " pyjwt python-multipart"
              " 'pydantic[email]'")),
            ("alembic upgrade head",
             f"PYTHONPATH=/app GL_DATABASE_URL='{PG_URL}' alembic upgrade head"),
            ("seed_gear",
             f"PYTHONPATH=/app GL_DATABASE_URL='{PG_URL}' python -m app.seeds.seed_gear"),
            ("seed_routes",
             f"PYTHONPATH=/app GL_DATABASE_URL='{PG_URL}' python -m app.seeds.seed_routes"),
            ("seed_kb",
             (f"PYTHONPATH=/app GL_DATABASE_URL='{PG_URL}' GL_KB_CSV=/app/route_guides.csv"
              " python -m app.seeds.seed_kb")),
            ("smoke checks", f"PYTHONPATH=/app python - <<'PYEOF'\n{SMOKE}\nPYEOF"),
        ]
        for name, cmd in steps:
            r = ctr.exec_run(["/bin/sh", "-c", f"cd /app && {cmd}"], demux=False)
            out = r.output.decode("utf-8", "replace").strip()
            tail = "\n    ".join(out.splitlines()[-12:]) if out else "(no output)"
            print(f"[4] {name}: exit={r.exit_code}\n    {tail}")
            results.append((name, r.exit_code == 0))
    finally:
        ctr.remove(force=True)
        print(f"[5] container {INTEGRATION} removed")

    print("\n===== SUMMARY =====")
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    all_ok = all(ok for _, ok in results)
    print("RESULT:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
