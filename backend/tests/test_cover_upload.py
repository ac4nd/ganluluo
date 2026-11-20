"""M8.8-covers-minio：封面文件名-路线名匹配 + run_upload 核心流程（Fake 网络层，不真连 MinIO）。

MinIO 网络路径（ensure_bucket/set_bucket_policy/put_object 真连 47.107.160.31）标注
defer 真机验证——服务器可达时跑 `python scripts/upload_covers.py --limit 3` 冒烟 +
全量，本文件只覆盖可离线回归的匹配/回写/断点续传语义。
"""
from pathlib import Path

from sqlalchemy import select

from app.models.route import Route
from app.seeds.seed_routes_csv import build_update_fields
from scripts.upload_covers import collect_covers, csv_names_by_seq, match_route, run_upload

BASE_URL = "http://minio.test/ganluluo-covers"


class FakeCoversStore:
    """run_upload 注入替身：记录 put_object 调用（同签名 Fake 网络层）。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.objects: dict[str, bytes] = {}

    async def put_object(self, key: str, data: bytes, content_type: str) -> None:
        self.calls.append((key, content_type))
        self.objects[key] = data


def make_covers(tmp_path: Path, names: list[str]) -> Path:
    covers = tmp_path / "covers"
    covers.mkdir(parents=True, exist_ok=True)
    for n in names:
        (covers / n).write_bytes(b"fake-jpeg-" + n.encode())
    return covers


# ---------- match_route：双向包含 + 唯一命中 ----------

ROUTES = [(1, "雨崩徒步（神瀑+冰湖精华线）"), (2, "虎跳峡高路徒步（一日精华版）"),
          (3, "五台山顺时针大朝台"), (4, "五台山逆时针小朝台")]


def test_match_route_bidirectional_contains():
    # 精确同名
    assert match_route("雨崩徒步（神瀑+冰湖精华线）", ROUTES) == 1
    # 文件名比 DB name 短（截断差异）：file_name[:10] 前缀包含
    assert match_route("虎跳峡高路徒步", ROUTES) == 2
    # DB name 比文件名短：反向包含（name in file_name）
    assert match_route("五台山顺时针大朝台（两日重装·详细版）", ROUTES) == 3


def test_match_route_ambiguous_or_missing_returns_none():
    # 「五台山顺时针大朝台」[:10] = "五台山顺时针大朝台"（9 字）只命中 id=3：
    # in "五台山顺时针大朝台" True；in "五台山逆时针小朝台" False → 唯一
    assert match_route("五台山顺时针大朝台", ROUTES) == 3
    # 多候选 → None（唯一性破坏，进 unmatched 人工兜底）
    ambiguous = [(5, "武功山反穿"), (6, "武功山反穿（金顶线）")]
    assert match_route("武功山反穿", ambiguous) is None
    # 无匹配
    assert match_route("完全无关的路线", ROUTES) is None
    # 空文件名片段
    assert match_route("", ROUTES) is None


# ---------- collect_covers：文件名规约过滤 ----------

def test_collect_covers_filters_and_sorts(tmp_path):
    covers = make_covers(tmp_path, ["0002_虎跳峡高路徒步.jpg", "0001_雨崩.jpg",
                                    "not-a-cover.jpg", "12_短序号.jpg", "0003_五台山.png"])
    got = collect_covers(covers)
    assert got == [(1, "雨崩", covers / "0001_雨崩.jpg"),
                   (2, "虎跳峡高路徒步", covers / "0002_虎跳峡高路徒步.jpg")]


def test_csv_names_by_seq():
    rows = [{"路线名称": "甲线"}, {"路线名称": " 乙线（备注） "}]
    assert csv_names_by_seq(rows) == {1: "甲线", 2: "乙线（备注）"}


# ---------- run_upload：上传 + cover_url 回写 + 断点续传 + dry-run ----------

async def seed_routes(db) -> None:
    db.add(Route(name="雨崩徒步（神瀑+冰湖精华线）", region="云南", sport="hiking", distance_km=26.7))
    db.add(Route(name="虎跳峡高路徒步（一日精华版）", region="云南", sport="hiking", distance_km=14.0))
    db.add(Route(name="无封面文件的路线", region="山西", sport="hiking", distance_km=10.0))
    await db.commit()


async def test_run_upload_uploads_and_writes_cover_url(db, tmp_path):
    await seed_routes(db)
    covers = make_covers(tmp_path, ["0001_雨崩.jpg", "0002_虎跳峡高路徒步.jpg", "9999_未匹配.jpg"])
    store = FakeCoversStore()

    stats = await run_upload(db, store, covers, BASE_URL)

    assert (stats.scanned, stats.matched, stats.uploaded, stats.resumed, stats.unmatched) == (3, 2, 2, 0, 1)
    assert stats.unmatched_files == ["9999_未匹配.jpg"]
    # 上传 key 按 route id + content_type
    assert sorted(store.calls) == [("covers/1.jpg", "image/jpeg"), ("covers/2.jpg", "image/jpeg")]
    # cover_url 回写（参数化 UPDATE 落库）
    rows = dict((await db.execute(select(Route.id, Route.cover_url))).all())
    assert rows[1] == f"{BASE_URL}/covers/1.jpg"
    assert rows[2] == f"{BASE_URL}/covers/2.jpg"
    assert rows[3] is None  # 无封面文件不回写


async def test_run_upload_resume_skips_correct_url(db, tmp_path):
    await seed_routes(db)
    covers = make_covers(tmp_path, ["0001_雨崩.jpg", "0002_虎跳峡高路徒步.jpg"])
    store = FakeCoversStore()
    await run_upload(db, store, covers, BASE_URL)

    # 二跑：cover_url 已对 → 全部 resumed，不再上传
    store2 = FakeCoversStore()
    stats2 = await run_upload(db, store2, covers, BASE_URL)
    assert (stats2.matched, stats2.uploaded, stats2.resumed) == (2, 0, 2)
    assert store2.calls == []

    # base_url 变了（换 endpoint/bucket）→ 视为未续传，重新上传覆盖
    stats3 = await run_upload(db, FakeCoversStore(), covers, "http://other.test/bkt")
    assert (stats3.uploaded, stats3.resumed) == (2, 0)


async def test_run_upload_dry_run_no_side_effects(db, tmp_path):
    await seed_routes(db)
    covers = make_covers(tmp_path, ["0001_雨崩.jpg", "9999_未匹配.jpg"])
    store = FakeCoversStore()

    stats = await run_upload(db, store, covers, BASE_URL, dry_run=True)

    assert (stats.matched, stats.uploaded, stats.unmatched) == (1, 0, 1)
    assert store.calls == []
    rows = dict((await db.execute(select(Route.id, Route.cover_url))).all())
    assert rows[1] is None  # 未写库


async def test_run_upload_limit(db, tmp_path):
    await seed_routes(db)
    covers = make_covers(tmp_path, ["0001_雨崩.jpg", "0002_虎跳峡高路徒步.jpg"])
    store = FakeCoversStore()
    stats = await run_upload(db, store, covers, BASE_URL, limit=1)
    assert (stats.scanned, stats.uploaded) == (1, 1)
    assert sorted(store.calls) == [("covers/1.jpg", "image/jpeg")]


async def test_run_upload_seq_fallback_resolves_ambiguity(db, tmp_path):
    """多候选歧义（同名变体路线）时序号兜底：CSV 行名精确相等唯一命中。"""
    db.add(Route(name="武功山反穿（龙山村→金顶）", region="江西", sport="hiking", distance_km=25.0))
    db.add(Route(name="武功山反穿越野跑（萍乡·草甸跑山殿堂线）", region="江西", sport="hiking",
                 distance_km=21.0))
    await db.commit()
    # 「武功山反穿」[:10] 前缀命中两条 → 名字匹配歧义
    covers = make_covers(tmp_path, ["0002_武功山反穿.jpg"])
    csv_names = {2: "武功山反穿越野跑（萍乡·草甸跑山殿堂线）"}  # 行号 2 → 野跑变体
    store = FakeCoversStore()
    stats = await run_upload(db, store, covers, BASE_URL, csv_names=csv_names)
    assert (stats.matched, stats.uploaded, stats.unmatched) == (1, 1, 0)
    assert store.calls == [("covers/2.jpg", "image/jpeg")]
    url = (await db.execute(select(Route.cover_url).where(Route.id == 2))).scalar_one()
    assert url == f"{BASE_URL}/covers/2.jpg"

    # 相关性校验防错位：文件名与 CSV 行名不相关 → 不兜底，进 unmatched（换干净目录）
    covers3 = make_covers(tmp_path / "c3", ["0003_无关键词.jpg"])
    stats3 = await run_upload(db, FakeCoversStore(), covers3, BASE_URL,
                              csv_names={3: "武功山反穿越野跑（萍乡·草甸跑山殿堂线）"})
    assert (stats3.matched, stats3.unmatched) == (0, 1)


# ---------- seed 同步：build_update_fields（同名行更新集） ----------

def test_build_update_fields_only_nonempty_parsed():
    # 全解析成功
    fields = build_update_fields({"里程(km)": "约12.5km", "累计爬升(m)": "约1918.3m",
                                  "难度(1-5)": "2.5/5", "建议用时": "4.5-6h",
                                  "轨迹清晰度": "高（指示牌）", "地形构成": "石板路",
                                  "安全提醒": "雨天路滑"})
    assert fields == {"distance_km": 12.5, "climb_m": 1918, "difficulty": 2, "duration_h": 4.5,
                      "clarity": "high", "terrain": [{"type": "石板路", "pct": 0}],
                      "warning": "雨天路滑"}


def test_build_update_fields_parse_fail_excluded():
    # 解析失败/原文空 → 不进更新集（安全默认 0/1/None 不覆盖既有值）
    fields = build_update_fields({"里程(km)": "组别以现场公布为准", "累计爬升(m)": "",
                                  "难度(1-5)": "未知", "建议用时": "体验段半天",
                                  "轨迹清晰度": "", "地形构成": "", "安全提醒": ""})
    assert fields == {}


def test_build_update_fields_warning_truncated():
    fields = build_update_fields({"安全提醒": "长" * 300})
    assert fields["warning"] == "长" * 255  # 同 build_route 的 _trunc 口径


# ---------- seed 同步流程：同名行更新（M8.8 语义），统计键保持兼容 ----------

async def test_seed_same_name_row_updates_nonempty_fields(db, tmp_path, monkeypatch):
    from app.seeds import seed_routes_csv

    # 预置「手工种子」同名行（track_points 演示数据）
    db.add(Route(name="手工线（测试）", region="手工地区", sport="hiking", distance_km=25.0,
                 track_points=[{"lat": 30.0, "lon": 100.0}]))
    await db.commit()

    csv_file = tmp_path / "routes.csv"
    csv_file.write_text(
        "\ufeff路线名称,运动类型,所在地区,里程(km),累计爬升(m),难度(1-5),建议用时,轨迹清晰度,地形构成,安全提醒\n"
        "手工线（测试）,徒步,云南迪庆,约12.5km,,2.5/5,4.5-6h,高,石板路,雨天路滑\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(seed_routes_csv, "CSV_PATH", csv_file)

    # 统计键保持 rows/added/skipped/warnings 四键（既有调用方/断言兼容；updated 走打印）
    stats = await seed_routes_csv.seed_routes_csv(db)
    assert stats == {"rows": 1, "added": 0, "skipped": 1, "warnings": 0}

    row = (await db.execute(select(Route).where(Route.name == "手工线（测试）"))).scalar_one()
    assert row.distance_km == 12.5      # 非空解析字段覆盖
    assert row.climb_m == 0             # 爬升解析失败 → 不更新（保安全默认 0）
    assert row.difficulty == 2
    assert row.duration_h == 4.5
    assert row.clarity == "high"
    assert row.terrain == [{"type": "石板路", "pct": 0}]
    assert row.warning == "雨天路滑"
    assert row.track_points == [{"lat": 30.0, "lon": 100.0}]  # 清单外字段保留
    assert row.region == "手工地区"      # region 不在更新清单（M8.8 字段口径）
