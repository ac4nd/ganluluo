"""媒体对象存储抽象（M6-media Task 1）。

MediaStore 协议 + MinIO 实现 + 离线 Fake 降级：get_media_store() 与
get_embedder() 同模式——GL_MINIO_* 四项配置齐全走 MinioMediaStore，
否则内存 FakeMediaStore（本地开发/测试离线可用）。降级必须有告警日志；
env=prod 时漏配直接 fail-fast（静默 Fake 会让 presign 产出废 URL 全域失效）。
"""
import logging
from datetime import timedelta
from typing import Protocol

from minio import Minio

logger = logging.getLogger(__name__)


class MediaStore(Protocol):
    def presign_put(self, key: str, content_type: str, expires_s: int) -> str: ...

    def presign_get(self, key: str, expires_s: int) -> str: ...

    def remove(self, key: str) -> None: ...

    # head_bytes：n 必须 >= 1（两个实现统一在入口校验，n < 1 → ValueError；
    # M6 Task 2 审查交接项，登记端点固定读 16 字节）
    def head_bytes(self, key: str, n: int) -> bytes: ...


class MinioMediaStore:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str,
                 secure: bool = False) -> None:
        self.bucket = bucket
        self._client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        # 幂等：已存在则跳过创建（bucket_exists + make_bucket）
        if not self._client.bucket_exists(self.bucket):
            self._client.make_bucket(self.bucket)

    def presign_put(self, key: str, content_type: str, expires_s: int) -> str:
        # MinIO PUT 预签 URL 不签 Content-Type（presigned_put_object 无此参数），
        # content_type 仅作为接口约定留存；上传端需发送一致的头（下载侧 mime 以 DB 为准）。
        return self._client.presigned_put_object(self.bucket, key, expires=timedelta(seconds=expires_s))

    def presign_get(self, key: str, expires_s: int) -> str:
        return self._client.presigned_get_object(self.bucket, key, expires=timedelta(seconds=expires_s))

    def remove(self, key: str) -> None:
        self._client.remove_object(self.bucket, key)

    def head_bytes(self, key: str, n: int) -> bytes:
        if n < 1:
            raise ValueError("n must be positive")
        # get_object 返回 urllib3.HTTPResponse：SDK 文档惯例 with 管理 + close/release_conn
        resp = self._client.get_object(self.bucket, key, offset=0, length=n)
        try:
            with resp:
                return resp.read(n)
        finally:
            resp.close()
            resp.release_conn()


class FakeMediaStore:
    """内存 dict 实现：测试/离线降级用；presign 前缀可注入（默认 https://fake.test）。"""

    def __init__(self, prefix: str = "https://fake.test") -> None:
        self.prefix = prefix
        self._objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        """测试辅助：直接写入对象内容（生产实现无此方法）。"""
        self._objects[key] = data

    def presign_put(self, key: str, content_type: str, expires_s: int) -> str:
        return f"{self.prefix}/put/{key}"

    def presign_get(self, key: str, expires_s: int) -> str:
        return f"{self.prefix}/get/{key}"

    def remove(self, key: str) -> None:
        # S3 DELETE 幂等语义：键不存在也不报错
        self._objects.pop(key, None)

    def head_bytes(self, key: str, n: int) -> bytes:
        if n < 1:
            raise ValueError("n must be positive")
        # key 不存在 → KeyError（登记端点统一兜成 HTTP 404）
        return self._objects[key][:n]


_store: MediaStore | None = None


def get_media_store() -> MediaStore:
    global _store
    if _store is None:
        from app.core.config import get_settings

        s = get_settings()
        if s.minio_endpoint and s.minio_access_key and s.minio_secret_key and s.minio_bucket:
            _store = MinioMediaStore(
                s.minio_endpoint,
                s.minio_access_key,
                s.minio_secret_key,
                s.minio_bucket,
                secure=s.minio_secure,
            )
        else:
            # 生产漏配 fail-fast：静默降级 Fake 会让 presign 返回废 URL（全域媒体失效）且零告警
            if s.env == "prod":
                raise RuntimeError(
                    "MinIO 未配置（GL_MINIO_ENDPOINT/ACCESS_KEY/SECRET_KEY/BUCKET），"
                    "生产环境不允许媒体存储降级为内存 Fake"
                )
            logger.warning("MinIO 未配置，媒体存储降级为内存 Fake（生产不可用）")
            _store = FakeMediaStore()  # 未配置 → 离线降级（同 get_embedder 的 Fake 分支）
    return _store


def reset_media_store() -> None:
    """清空单例缓存：get_settings.cache_clear() 后同步调用（测试/配置热更）。"""
    global _store
    _store = None
