import pytest

from app.core.config import get_settings
from app.domains.media.media_store import FakeMediaStore, get_media_store, reset_media_store

KEY = "videos/0123456789abcdef.mp4"


def test_fake_roundtrip_head_bytes():
    store = FakeMediaStore()
    store.put(KEY, b"MMdef-xyz")
    assert store.head_bytes(KEY, 3) == b"MMd"
    # n 超过对象大小：返回整个对象（head 语义，不越界报错）
    assert store.head_bytes(KEY, 100) == b"MMdef-xyz"


def test_fake_presign_contains_key():
    store = FakeMediaStore()
    put_url = store.presign_put(KEY, "video/mp4", 600)
    get_url = store.presign_get(KEY, 600)
    assert "put" in put_url and KEY in put_url
    assert "get" in get_url and KEY in get_url


def test_fake_presign_prefix_injectable():
    store = FakeMediaStore(prefix="http://localhost:9000")
    assert store.presign_put(KEY, "video/mp4", 1).startswith("http://localhost:9000/")
    assert store.presign_get(KEY, 1).startswith("http://localhost:9000/")


def test_fake_remove_is_idempotent():
    store = FakeMediaStore()
    store.put(KEY, b"data")
    store.remove(KEY)
    store.remove(KEY)  # S3 DELETE 幂等：键不存在不报错
    with pytest.raises(KeyError):
        store.head_bytes(KEY, 1)


def test_fake_head_bytes_missing_key_raises():
    store = FakeMediaStore()
    with pytest.raises(KeyError):
        store.head_bytes("videos/ghost.mp4", 4)


def test_head_bytes_rejects_non_positive_n():
    # M6 Task 2 审查交接：登记端点固定 head 16 字节，n>=1 防护在 store 层统一兜底
    store = FakeMediaStore()
    store.put(KEY, b"data")
    with pytest.raises(ValueError):
        store.head_bytes(KEY, 0)
    with pytest.raises(ValueError):
        store.head_bytes(KEY, -1)


def test_get_media_store_unconfigured_falls_back_to_fake(monkeypatch):
    # 显式置空四项（环境变量优先于 .env 文件），保证"未配置"语义
    for name in ("GL_MINIO_ENDPOINT", "GL_MINIO_ACCESS_KEY", "GL_MINIO_SECRET_KEY", "GL_MINIO_BUCKET"):
        monkeypatch.setenv(name, "")
    get_settings.cache_clear()
    reset_media_store()
    try:
        assert isinstance(get_media_store(), FakeMediaStore)
    finally:
        # 恢复缓存，避免污染其他测试的 settings/store 单例
        get_settings.cache_clear()
        reset_media_store()
