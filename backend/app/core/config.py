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


@lru_cache
def get_settings() -> Settings:
    return Settings()
