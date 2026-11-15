"""媒体对象存储抽象（M6-media Task 1 / M6.5-polish I-6 async 化）。

MediaStore 协议 + MinIO 实现 + 离线 Fake 降级：get_media_store() 与
get_embedder() 同模式——GL_MINIO_* 四项配置齐全走 MinioMediaStore，
否则内存 FakeMediaStore（本地开发/测试离线可用）。降级必须有告警日志；
env=prod 时漏配直接 fail-fast（静默 Fake 会让 presign 产出废 URL 全域失效）。

I-6（M6.5）：协议方法除 presign_put（本地 HMAC 无网络 IO，保持同步）外全部
async 化；MinioMediaStore 的 SDK 网络调用统一 asyncio.to_thread 包裹，避免
阻塞事件循环。建桶从 sync 构造函数迁至 async 工厂内 await（构造期网络 IO
同样会阻塞事件循环），presign 放行前 bucket 必就绪。
"""
import asyncio
import logging
from datetime import timedelta
from typing import Protocol

from minio import Minio

logger = logging.getLogger(__name__)


class MediaStore(Protocol):
    # presign_put：本地 HMAC 签名，无网络 IO，保持同步（其余方法 async，I-6）。
    def presign_put(self, key: str, content_type: str, expires_s: int) -> str: ...

    async def presign_get(self, key: str, expires_s: int) -> str: ...

    async def remove(self, key: str) -> None: ...

    # head_bytes：n 必须 >= 1（两个实现统一在入口校验，n < 1 → ValueError；
    # M6 Task 2 审查交接项，登记端点固定读 16 字节）
    async def head_bytes(self, key: str, n: int) -> bytes: ...

    # I-2（M6.5）：登记时核对象真实字节数（MinIO stat_object().size；Fake len(bytes)），
    # 客户端登记声明的 size 不得再作为落库依据。
    async def stat(self, key: str) -> int: ...


class MinioMediaStore:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str,
                 secure: bool = False) -> None:
        self.bucket = bucket
        # Minio 客户端构造是纯本地（无网络 IO）；建桶迁至 async ensure_bucket
        # （I-6：构造期同步网络 IO 会阻塞事件循环），由 get_media_store() 工厂 await。
        self._client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        self._bucket_ready = False

    async def ensure_bucket(self) -> None:
        """幂等建桶：已存在则跳过创建（bucket_exists + make_bucket）。

        get_media_store() 单例创建时 await 一次——presign_put 无网络 IO 不会建桶，
        必须在把预签 URL 交给客户端 PUT 之前保证 bucket 就绪（原构造函数语义）。
        """
        if self._bucket_ready:
            return
        if not await asyncio.to_thread(self._client.bucket_exists, self.bucket):
            await asyncio.to_thread(self._client.make_bucket, self.bucket)
        self._bucket_ready = True

    def presign_put(self, key: str, content_type: str, expires_s: int) -> str:
        # 本地 HMAC 无网络 IO，保持同步（I-6）。
        # MinIO PUT 预签 URL 不签 Content-Type（presigned_put_object 无此参数），
        # content_type 仅作为接口约定留存；上传端需发送一致的头（下载侧 mime 以 DB 为准）。
        return self._client.presigned_put_object(self.bucket, key, expires=timedelta(seconds=expires_s))

    async def presign_get(self, key: str, expires_s: int) -> str:
        # presigned_get_object 同为本地签名，按 I-6 brief 统一 to_thread 包裹
        return await asyncio.to_thread(
            self._client.presigned_get_object, self.bucket, key, expires=timedelta(seconds=expires_s)
        )

    async def remove(self, key: str) -> None:
        await asyncio.to_thread(self._client.remove_object, self.bucket, key)

    async def head_bytes(self, key: str, n: int) -> bytes:
        if n < 1:
            raise ValueError("n must be positive")
        # get_object 返回 urllib3.HTTPResponse：SDK 文档惯例 with 管理 + close/release_conn；
        # 连接建立与响应读取均为网络 IO → to_thread（close/release_conn 是本地归还连接池）
        resp = await asyncio.to_thread(self._client.get_object, self.bucket, key, offset=0, length=n)
        try:
            with resp:
                return await asyncio.to_thread(resp.read, n)
        finally:
            resp.close()
            resp.release_conn()

    async def stat(self, key: str) -> int:
        # I-2：对象真实字节数（登记核大小用）；key 不存在 → S3Error(NoSuchKey)。
        # minio SDK 标注 size: int | None（已上传对象实际必有值），None 兜底 0 →
        # 登记侧必判"大小与声明不符"422，不静默放行。
        size = (await asyncio.to_thread(self._client.stat_object, self.bucket, key)).size
        return 0 if size is None else size


class FakeMediaStore:
    """内存 dict 实现：测试/离线降级用；presign 前缀可注入（默认 https://fake.test）。

    I-6：协议方法签名 async 化——实现体保持同步逻辑不变，仅改签名（纯内存无 IO）。
    """

    def __init__(self, prefix: str = "https://fake.test") -> None:
        self.prefix = prefix
        self._objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        """测试辅助：直接写入对象内容（生产实现无此方法，保持同步）。"""
        self._objects[key] = data

    def presign_put(self, key: str, content_type: str, expires_s: int) -> str:
        return f"{self.prefix}/put/{key}"

    async def presign_get(self, key: str, expires_s: int) -> str:
        return f"{self.prefix}/get/{key}"

    async def remove(self, key: str) -> None:
        # S3 DELETE 幂等语义：键不存在也不报错
        self._objects.pop(key, None)

    async def head_bytes(self, key: str, n: int) -> bytes:
        if n < 1:
            raise ValueError("n must be positive")
        # key 不存在 → KeyError（登记端点统一兜成 HTTP 404）
        return self._objects[key][:n]

    async def stat(self, key: str) -> int:
        # I-2：内存实现即 len(bytes)；key 不存在 → KeyError（同 head_bytes 语义）
        return len(self._objects[key])


_store: MediaStore | None = None


async def get_media_store() -> MediaStore:
    """store 单例（I-6 改 async 工厂）：MinIO 构造后 await ensure_bucket() 再入缓存，
    保证 presign 放行前 bucket 就绪；Fake 分支无 IO。"""
    global _store
    if _store is None:
        from app.core.config import get_settings

        s = get_settings()
        if s.minio_endpoint and s.minio_access_key and s.minio_secret_key and s.minio_bucket:
            store = MinioMediaStore(
                s.minio_endpoint,
                s.minio_access_key,
                s.minio_secret_key,
                s.minio_bucket,
                secure=s.minio_secure,
            )
            await store.ensure_bucket()
            _store = store
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
