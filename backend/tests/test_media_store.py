import logging

import pytest

from app.core.config import get_settings
from app.domains.media.media_store import FakeMediaStore, get_media_store, reset_media_store

KEY = "videos/0123456789abcdef.mp4"


async def test_fake_roundtrip_head_bytes():
    store = FakeMediaStore()
    store.put(KEY, b"MMdef-xyz")
    assert await store.head_bytes(KEY, 3) == b"MMd"
    # n 超过对象大小：返回整个对象（head 语义，不越界报错）
    assert await store.head_bytes(KEY, 100) == b"MMdef-xyz"


def test_fake_presign_put_stays_sync():
    # I-6：presign_put 本地 HMAC 无网络 IO，保持同步
    store = FakeMediaStore()
    assert KEY in store.presign_put(KEY, "video/mp4", 600)


async def test_fake_presign_contains_key():
    store = FakeMediaStore()
    put_url = store.presign_put(KEY, "video/mp4", 600)
    get_url = await store.presign_get(KEY, 600)
    assert "put" in put_url and KEY in put_url
    assert "get" in get_url and KEY in get_url


async def test_fake_presign_prefix_injectable():
    store = FakeMediaStore(prefix="http://localhost:9000")
    assert store.presign_put(KEY, "video/mp4", 1).startswith("http://localhost:9000/")
    assert (await store.presign_get(KEY, 1)).startswith("http://localhost:9000/")


async def test_fake_remove_is_idempotent():
    store = FakeMediaStore()
    store.put(KEY, b"data")
    await store.remove(KEY)
    await store.remove(KEY)  # S3 DELETE 幂等：键不存在不报错
    with pytest.raises(KeyError):
        await store.head_bytes(KEY, 1)


async def test_fake_stat_returns_byte_length():
    # I-2：stat 返回对象真实字节数；缺 key → KeyError（同 head_bytes 语义）
    store = FakeMediaStore()
    store.put(KEY, b"12345678")
    assert await store.stat(KEY) == 8
    with pytest.raises(KeyError):
        await store.stat("videos/ghost.mp4")


async def test_fake_head_bytes_missing_key_raises():
    store = FakeMediaStore()
    with pytest.raises(KeyError):
        await store.head_bytes("videos/ghost.mp4", 4)


async def test_head_bytes_rejects_non_positive_n():
    # M6 Task 2 审查交接：登记端点固定 head 16 字节，n>=1 防护在 store 层统一兜底
    store = FakeMediaStore()
    store.put(KEY, b"data")
    with pytest.raises(ValueError):
        await store.head_bytes(KEY, 0)
    with pytest.raises(ValueError):
        await store.head_bytes(KEY, -1)


async def test_get_media_store_unconfigured_falls_back_to_fake(monkeypatch, caplog):
    # 显式置空四项（环境变量优先于 .env 文件），保证"未配置"语义；dev 下允许降级但不许静默
    for name in ("GL_MINIO_ENDPOINT", "GL_MINIO_ACCESS_KEY", "GL_MINIO_SECRET_KEY", "GL_MINIO_BUCKET"):
        monkeypatch.setenv(name, "")
    get_settings.cache_clear()
    reset_media_store()
    try:
        with caplog.at_level(logging.WARNING, logger="app.domains.media.media_store"):
            store = await get_media_store()
        assert isinstance(store, FakeMediaStore)  # dev 缺配置 → Fake 且不抛
        assert any("MinIO 未配置" in r.message for r in caplog.records)  # 降级必须有告警
    finally:
        # 恢复缓存，避免污染其他测试的 settings/store 单例
        get_settings.cache_clear()
        reset_media_store()


async def test_get_media_store_prod_missing_config_fails_fast(monkeypatch):
    # prod + 漏配 → RuntimeError fail-fast：静默 Fake 会让 presign 返回废 URL 全域失效且零告警
    monkeypatch.setenv("GL_ENV", "prod")
    for name in ("GL_MINIO_ENDPOINT", "GL_MINIO_ACCESS_KEY", "GL_MINIO_SECRET_KEY", "GL_MINIO_BUCKET"):
        monkeypatch.setenv(name, "")
    get_settings.cache_clear()
    reset_media_store()
    try:
        with pytest.raises(RuntimeError, match="MinIO"):
            await get_media_store()
    finally:
        # 恢复缓存，避免污染其他测试的 settings/store 单例
        get_settings.cache_clear()
        reset_media_store()
