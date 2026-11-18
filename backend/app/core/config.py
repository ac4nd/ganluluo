from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="GL_", extra="ignore")

    env: str = "dev"
    database_url: str = "sqlite+aiosqlite:///./dev.db"
    jwt_secret: str = "dev-secret-change-me-32bytes-min"
    jwt_alg: str = "HS256"
    access_ttl_min: int = 15
    refresh_ttl_days: int = 7
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    admin_email: str = ""
    # MinIO 对象存储：四项齐全启用 MinioMediaStore，否则离线降级 FakeMediaStore
    minio_endpoint: str = ""
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = ""
    minio_secure: bool = False  # GL_MINIO_SECURE：MinIO 是否走 TLS（https）
    # 微信小程序一键登录（M8）：两项齐全走真实 jscode2session；
    # 未配置时 dev 降级确定性 mock（openid=wxmock_+sha256(code)[:24]），prod 拒绝 503
    wechat_appid: str = ""
    wechat_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
