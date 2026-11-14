"""M4.5 Task 2：POST /tracks GPX 上传管线（同步处理）。

GPX 夹具复用 test_track_service 的模块级 GPX 常量；上传目录 monkeypatch 到
tmp_path（同 test_track_store 先例），不污染真实 backend/uploads/。
测试用户一律 register_and_login（无字面量凭据）。
"""

import textwrap

import pytest
from sqlalchemy import select

from app.domains.sports import track_store
from app.models.route import Route
from app.models.track import RouteTrack
from app.seeds.seed_routes import seed_routes

from .test_auth_login import register_and_login
from .test_track_service import GPX

SINGLE_POINT_GPX = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <gpx version="1.1" creator="test">
      <trk><name>one</name><trkseg>
        <trkpt lat="30.1200" lon="118.8200"><ele>420</ele></trkpt>
      </trkseg></trk>
    </gpx>
    """)


@pytest.fixture()
def tmp_tracks_dir(tmp_path, monkeypatch):
    # 存储目录指到临时路径，测试不污染真实 backend/uploads/
    d = tmp_path / "tracks"
    monkeypatch.setattr(track_store, "uploads_dir", d)
    return d


async def _auth(client, email: str) -> dict[str, str]:
    tokens = await register_and_login(client, email=email)
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _upload_body(content: bytes, filename: str = "a.gpx") -> dict:
    return {"files": {"file": (filename, content, "application/gpx+xml")},
            "data": {"name": "测试轨迹", "region": "云南", "sport": "hiking"}}


async def _assert_no_rows(db, tmp_tracks_dir) -> None:
    assert (await db.execute(select(Route))).scalars().all() == []
    assert (await db.execute(select(RouteTrack))).scalars().all() == []
    assert list(tmp_tracks_dir.glob("*.gpx")) == []  # 校验失败也不落盘


async def test_upload_201_full_contract(client, db, tmp_tracks_dir):
    await seed_routes(db)
    h = await _auth(client, "track@b.com")
    r = await client.post("/tracks", headers=h, **_upload_body(GPX.encode("utf-8")))
    assert r.status_code == 201
    body = r.json()
    # TrackOut 契约：TrackSummary + 两 id，不多不少
    assert set(body) == {"route_id", "track_id", "points", "distance_km",
                         "climb_m", "difficulty", "clarity"}
    assert body["route_id"] > 0 and body["track_id"] > 0
    assert body["points"] == 5  # 原始点数
    assert body["distance_km"] > 0
    assert body["climb_m"] >= 90
    assert 1 <= body["difficulty"] <= 5
    assert body["clarity"] in {"low", "mid", "high"}

    # DB 断言（expire 强制从库重读，排除会话缓存干扰）
    db.expire_all()
    route = await db.get(Route, body["route_id"])
    assert route is not None
    assert route.status == "draft"
    assert route.sport == "hiking"
    assert route.duration_h == 0.0 and route.terrain == []  # 中性占位
    assert route.distance_km == body["distance_km"] and route.climb_m == body["climb_m"]
    assert route.difficulty == body["difficulty"] and route.clarity == body["clarity"]
    assert route.track_points and route.elevation  # process_track 已覆盖
    rt = (await db.execute(select(RouteTrack))).scalar_one()
    assert rt.route_id == body["route_id"]
    assert rt.processed is True
    assert rt.points == 5
    assert rt.gpx_object.startswith("tracks/") and rt.gpx_object.endswith(".gpx")

    # 草稿不进公开列表
    published = (await client.get("/routes")).json()
    assert published and all(row["id"] != body["route_id"] for row in published)

    # 文件落盘可读回（走 read_gpx 白名单校验 + 物理读取）
    assert track_store.read_gpx(rt.gpx_object) == GPX


async def test_upload_wrong_suffix_422(client, db, tmp_tracks_dir):
    h = await _auth(client, "suffix@b.com")
    r = await client.post("/tracks", headers=h, **_upload_body(GPX.encode("utf-8"), "a.txt"))
    assert r.status_code == 422
    assert r.json()["detail"] == "仅支持 .gpx 文件"
    await _assert_no_rows(db, tmp_tracks_dir)


async def test_upload_over_5mb_422(client, db, tmp_tracks_dir):
    # 大小校验先于解析：5MB+1 的非 XML 内容直接命中大小分支
    h = await _auth(client, "big@b.com")
    r = await client.post(
        "/tracks", headers=h, **_upload_body(b"\x00" * (5 * 1024 * 1024 + 1))
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "轨迹文件超过 5MB 上限"
    await _assert_no_rows(db, tmp_tracks_dir)


async def test_upload_non_utf8_422(client, db, tmp_tracks_dir):
    # \xff 非法 UTF-8：解码分支先于解析失败
    h = await _auth(client, "utf8@b.com")
    r = await client.post("/tracks", headers=h, **_upload_body(b"\xff\xfe not utf8"))
    assert r.status_code == 422
    assert r.json()["detail"] == "文件必须是 UTF-8 编码的文本"
    await _assert_no_rows(db, tmp_tracks_dir)


async def test_upload_unparseable_422(client, db, tmp_tracks_dir):
    h = await _auth(client, "bad@b.com")
    r = await client.post("/tracks", headers=h, **_upload_body(b"this is not xml"))
    assert r.status_code == 422
    assert r.json()["detail"].startswith("GPX 解析失败")
    await _assert_no_rows(db, tmp_tracks_dir)


async def test_upload_single_point_422(client, db, tmp_tracks_dir):
    h = await _auth(client, "one@b.com")
    r = await client.post("/tracks", headers=h, **_upload_body(SINGLE_POINT_GPX.encode("utf-8")))
    assert r.status_code == 422
    assert r.json()["detail"] == "轨迹点不足"
    await _assert_no_rows(db, tmp_tracks_dir)


async def test_upload_unauthorized_401(client, tmp_tracks_dir):
    r = await client.post("/tracks", **_upload_body(GPX.encode("utf-8")))
    assert r.status_code == 401


async def test_upload_missing_file_404(client, db, tmp_tracks_dir, monkeypatch):
    # 防御性转换：落盘后读回缺失 → 404（同步流程本不会触发）。
    # 与校验失败不同：GPX 已落盘，但任何 DB 行都不该留下。
    def _missing(key: str) -> str:
        raise FileNotFoundError(key)

    monkeypatch.setattr(track_store, "read_gpx", _missing)
    h = await _auth(client, "gone@b.com")
    r = await client.post("/tracks", headers=h, **_upload_body(GPX.encode("utf-8")))
    assert r.status_code == 404
    assert (await db.execute(select(Route))).scalars().all() == []
    assert (await db.execute(select(RouteTrack))).scalars().all() == []
    assert list(tmp_tracks_dir.glob("*.gpx"))  # 文件已写，读回失败在落库前拦截
