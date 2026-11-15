import pytest

from app.domains.sports import track_store


@pytest.fixture()
def tmp_tracks_dir(tmp_path, monkeypatch):
    # 存储目录指到临时路径，测试不污染真实 backend/uploads/
    d = tmp_path / "tracks"
    monkeypatch.setattr(track_store, "uploads_dir", d)
    return d


def test_save_read_roundtrip(tmp_tracks_dir):
    content = b"<?xml version='1.0' encoding='UTF-8'?><gpx version='1.1'></gpx>"
    key = track_store.save_gpx(content)
    assert key.startswith("tracks/") and key.endswith(".gpx")
    assert track_store.read_gpx(key) == content.decode("utf-8")


def test_save_creates_missing_dir(tmp_path, monkeypatch):
    target = tmp_path / "nested" / "tracks"
    monkeypatch.setattr(track_store, "uploads_dir", target)
    assert not target.exists()
    key = track_store.save_gpx(b"<gpx/>")
    assert target.is_dir()
    assert (target / key.removeprefix("tracks/")).exists()


def test_read_gpx_rejects_invalid_keys(tmp_tracks_dir):
    bad_keys = [
        "../x.gpx",
        "tracks/../../etc/passwd",
        "任意串",
        "",
        "tracks/notahexvalue.gpx",
        "tracks/0123456789abcdef0123456789abcdef.txt",
        "other/0123456789abcdef0123456789abcdef.gpx",
        "tracks/0123456789ABCDEF0123456789ABCDEF.gpx",
    ]
    for key in bad_keys:
        with pytest.raises(ValueError):
            track_store.read_gpx(key)
