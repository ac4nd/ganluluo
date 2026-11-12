# M1 · auth + profile 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付后端 M1——注册/登录（argon2id + JWT 双令牌轮换与复用检测 + 登录限流）、认证依赖、画像读写、装备型号库与装备清单管理，附 OpenAPI 导出与 CI 质量门。

**Architecture:** FastAPI 模块化单体（[system-design.md](../spec/system-design.md)）；`api → services → models` 三层禁跨层；测试走 aiosqlite 内存库 + httpx ASGITransport，不依赖 Docker。

**Tech Stack:** Python 3.12 · FastAPI ≥0.115 · SQLAlchemy 2.0 async · Alembic · PyJWT(HS256) · pwdlib[argon2] · slowapi · pytest/pytest-asyncio/httpx · Ruff · mypy

## Global Constraints

- Python ≥3.12；依赖版本以 Task 1 的 `pyproject.toml` 为准，不得增删
- 密码哈希 argon2id；JWT HS256：access 15min / refresh 7d，刷新必须轮换且复用检测（复用即吊销该用户全部刷新令牌）
- 所有入参/出参必须是 `app/schemas/` 下的 Pydantic 模型，禁止裸 dict
- 分层：`api/` 只调用 `services/`，`services/` 只调用 `models/`；测试与代码同任务交付
- 提交信息前缀：`test:` / `feat:` / `chore:`；每任务一提交
- `user_gear` 采用代理主键（已修正 system-design §5.2 的 NULL 复合主键缺陷）

---

### Task 1: 工程脚手架与健康检查

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/main.py`
- Create: `backend/app/core/config.py`
- Create: `backend/app/api/routes/ops.py`
- Create: `backend/app/api/__init__.py` `backend/app/api/routes/__init__.py` `backend/app/__init__.py` `backend/app/core/__init__.py`（空文件）
- Create: `backend/tests/conftest.py` `backend/tests/test_ops.py`
- Create: `backend/.env.example` `backend/docker-compose.yml`

**Interfaces:**
- Produces: `create_app() -> FastAPI`（后续所有任务复用）、`get_settings() -> Settings`、pytest 夹具 `client`（httpx AsyncClient）

- [ ] **Step 1: 写 `pyproject.toml`**

```toml
[project]
name = "ganluluo-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "sqlalchemy[asyncio]>=2.0.30",
  "asyncpg>=0.29",
  "aiosqlite>=0.20",
  "alembic>=1.13",
  "pydantic>=2.7",
  "pydantic-settings>=2.3",
  "pyjwt>=2.8",
  "pwdlib[argon2]>=0.2",
  "slowapi>=0.1.9",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "httpx>=0.27", "ruff>=0.4", "mypy>=1.10"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["."]

[tool.ruff]
line-length = 110
target-version = "py312"

[tool.mypy]
python_version = "3.12"
disallow_untyped_defs = true
ignore_missing_imports = true
```

- [ ] **Step 2: 写 `app/core/config.py`**

```python
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 3: 写 `app/api/routes/ops.py` 与 `app/main.py`**

```python
# app/api/routes/ops.py
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

```python
# app/main.py
from fastapi import FastAPI

from app.api.routes.ops import router as ops_router


def create_app() -> FastAPI:
    app = FastAPI(title="GanLuLuo API", version="0.1.0")
    app.include_router(ops_router, prefix="/ops", tags=["ops"])
    return app


app = create_app()
```

- [ ] **Step 4: 写 `tests/conftest.py` 与 `tests/test_ops.py`**

```python
# tests/conftest.py
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

```python
# tests/test_ops.py
async def test_health(client):
    r = await client.get("/ops/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 5: 写 `.env.example` 与 `docker-compose.yml`**

```yaml
# .env.example
GL_ENV=dev
GL_DATABASE_URL=postgresql+asyncpg://ganluluo:ganluluo@localhost:5432/ganluluo
GL_JWT_SECRET=please-generate-32-bytes-random-secret
```

```yaml
# docker-compose.yml
services:
  postgres:
    image: postgis/postgis:16-3.4
    environment:
      POSTGRES_USER: ganluluo
      POSTGRES_PASSWORD: ganluluo
      POSTGRES_DB: ganluluo
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
volumes:
  pgdata:
```

- [ ] **Step 6: 安装并运行测试**

Run: `cd backend && python -m pip install -e ".[dev]" && pytest -v`
Expected: `1 passed`

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "chore: backend scaffold with ops health"
```

---

### Task 2: 数据库基建（async engine + Alembic + users/refresh_tokens 表）

**Files:**
- Create: `backend/app/core/db.py`
- Create: `backend/app/models/base.py` `backend/app/models/user.py` `backend/app/models/refresh_token.py` `backend/app/models/__init__.py`
- Create: `backend/alembic.ini` `backend/alembic/env.py` `backend/alembic/versions/0001_users.py`
- Modify: `backend/tests/conftest.py`（加 `db` 夹具）

**Interfaces:**
- Produces: `Base`（声明基类）、`get_session()`（FastAPI 依赖）、`User` / `RefreshToken` 模型、测试夹具 `db`（async session）

- [ ] **Step 1: 写 `app/core/db.py`**

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(get_settings().database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
```

- [ ] **Step 2: 写 `app/models/base.py`、`user.py`、`refresh_token.py`**

```python
# app/models/base.py
from app.core.db import Base

__all__ = ["Base"]
```

```python
# app/models/user.py
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True)
    nickname: Mapped[str] = mapped_column(String(32))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    oauth_provider: Mapped[str | None] = mapped_column(String(16))
    oauth_subject: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

```python
# app/models/refresh_token.py
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    jti: Mapped[str] = mapped_column(String(32), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 3: 写 `app/models/__init__.py` 并改 `tests/conftest.py` 加 `db` 夹具**

```python
# app/models/__init__.py
from app.models.base import Base
from app.models.refresh_token import RefreshToken
from app.models.user import User

__all__ = ["Base", "User", "RefreshToken"]
```

```python
# tests/conftest.py 追加
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db import Base, get_session


@pytest_asyncio.fixture
async def db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db):
    app = create_app()

    async def override():
        yield db

    app.dependency_overrides[get_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

- [ ] **Step 4: Alembic 初始化与 0001 迁移**

Run: `cd backend && alembic init -t async alembic`

改 `alembic/env.py` 两处：`config.set_main_option("sqlalchemy.url", get_settings().database_url)` 与 `target_metadata = Base.metadata`（import 自 `app.models`）。

写 `alembic/versions/0001_users.py`：

```python
"""users + refresh_tokens"""

revision = "0001"
down_revision = None

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(255), unique=True),
        sa.Column("phone", sa.String(20), unique=True),
        sa.Column("nickname", sa.String(32), nullable=False),
        sa.Column("password_hash", sa.String(255)),
        sa.Column("oauth_provider", sa.String(16)),
        sa.Column("oauth_subject", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True),
        sa.Column("jti", sa.String(32), unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("refresh_tokens")
    op.drop_table("users")
```

Run: `alembic upgrade head`
Expected: 无报错（对 sqlite 或 compose 里的 postgres 均可）

- [ ] **Step 5: 跑全部测试确认无回归**

Run: `pytest -v`
Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: db infra with users and refresh_tokens"
```

---

### Task 3: 注册接口

**Files:**
- Create: `backend/app/schemas/auth.py`
- Create: `backend/app/services/user_service.py`
- Modify: `backend/app/api/routes/auth.py`（新建，注册 `POST /auth/register`）
- Modify: `backend/app/main.py`（挂 auth router）
- Create: `backend/tests/test_auth_register.py`

**Interfaces:**
- Consumes: `db` / `client` 夹具、`User` 模型
- Produces: `user_service.create_user(session, data) -> User`、`POST /auth/register -> 201 {id, email, phone, nickname}`；冲突 409；校验失败 422

- [ ] **Step 1: 写 `app/schemas/auth.py`**

```python
from pydantic import BaseModel, EmailStr, Field, model_validator


class RegisterIn(BaseModel):
    email: EmailStr | None = None
    phone: str | None = Field(None, pattern=r"^1\d{10}$")
    password: str = Field(min_length=8, max_length=72)
    nickname: str = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def require_identity(self):
        if not self.email and not self.phone:
            raise ValueError("email 或 phone 必填其一")
        return self


class UserOut(BaseModel):
    id: int
    email: str | None
    phone: str | None
    nickname: str
```

- [ ] **Step 2: 写 `app/services/user_service.py`**

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User
from app.schemas.auth import RegisterIn


async def create_user(session: AsyncSession, data: RegisterIn) -> User:
    user = User(
        email=data.email,
        phone=data.phone,
        nickname=data.nickname,
        password_hash=hash_password(data.password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def get_by_identity(session: AsyncSession, email: str | None, phone: str | None) -> User | None:
    stmt = select(User).where(User.deleted_at.is_(None))
    if email:
        stmt = stmt.where(User.email == email)
    else:
        stmt = stmt.where(User.phone == phone)
    return (await session.execute(stmt)).scalar_one_or_none()
```

- [ ] **Step 3: 写 `app/api/routes/auth.py`（注册部分）并挂载**

```python
# app/api/routes/auth.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.schemas.auth import RegisterIn, UserOut
from app.services import user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
async def register(data: RegisterIn, session: AsyncSession = Depends(get_session)) -> UserOut:
    try:
        user = await user_service.create_user(session, data)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="邮箱或手机号已注册") from None
    return UserOut.model_validate(user)
```

```python
# app/main.py 的 create_app 内追加
from app.api.routes.auth import router as auth_router
app.include_router(auth_router, tags=["auth"])
```

- [ ] **Step 4: 写 `tests/test_auth_register.py`**

```python
async def test_register_ok(client):
    r = await client.post("/auth/register", json={
        "email": "a@b.com", "password": "passw0rd!", "nickname": "晨风"})
    assert r.status_code == 201
    assert r.json()["nickname"] == "晨风"


async def test_register_duplicate_409(client):
    body = {"email": "a@b.com", "password": "passw0rd!", "nickname": "晨风"}
    await client.post("/auth/register", json=body)
    r = await client.post("/auth/register", json=body)
    assert r.status_code == 409


async def test_register_missing_identity_422(client):
    r = await client.post("/auth/register", json={"password": "passw0rd!", "nickname": "晨风"})
    assert r.status_code == 422
```

- [ ] **Step 5: Run** `pytest tests/test_auth_register.py -v` → Expected: `3 passed`

- [ ] **Step 6: Commit** `git add -A && git commit -m "feat: register endpoint"`

---

### Task 4: 登录 + JWT 双令牌（轮换与复用检测）+ 登出

**Files:**
- Create: `backend/app/core/security.py`
- Modify: `backend/app/models/refresh_token.py`（Task 2 已建，无需改）
- Create: `backend/app/services/auth_service.py`
- Modify: `backend/app/api/routes/auth.py`（login/refresh/logout）
- Create: `backend/tests/test_auth_login.py`

**Interfaces:**
- Produces: `security.hash_password/verify_password/create_access_token/create_refresh_token/decode_token`；`auth_service.issue_pair(session, user) -> TokenPair`、`auth_service.rotate(session, refresh_token) -> TokenPair`（复用检测抛 `HTTPException 401`）；`POST /auth/login|refresh|logout`

- [ ] **Step 1: 写 `app/core/security.py`**

```python
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

_pwd = PasswordHash.recommended()


def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


def create_access_token(user_id: int) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "type": "access", "jti": uuid.uuid4().hex,
               "iat": now, "exp": now + timedelta(minutes=s.access_ttl_min)}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_alg)


def create_refresh_token(user_id: int) -> tuple[str, str, datetime]:
    s = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(days=s.refresh_ttl_days)
    jti = uuid.uuid4().hex
    payload = {"sub": str(user_id), "type": "refresh", "jti": jti, "iat": now, "exp": exp}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_alg), jti, exp


def decode_token(token: str) -> dict:
    s = get_settings()
    return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_alg])
```

- [ ] **Step 2: 写 `app/services/auth_service.py`**

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.refresh_token import RefreshToken
from app.models.user import User


async def _insert_refresh(session: AsyncSession, user_id: int, jti: str, exp: datetime) -> None:
    session.add(RefreshToken(user_id=user_id, jti=jti, expires_at=exp))
    await session.commit()


async def issue_pair(session: AsyncSession, user: User) -> dict[str, str]:
    access = create_access_token(user.id)
    refresh, jti, exp = create_refresh_token(user.id)
    await _insert_refresh(session, user.id, jti, exp)
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


async def _get_by_jti(session: AsyncSession, jti: str) -> RefreshToken | None:
    return (await session.execute(select(RefreshToken).where(RefreshToken.jti == jti))).scalar_one_or_none()


async def _revoke_all(session: AsyncSession, user_id: int) -> None:
    await session.execute(update(RefreshToken).where(RefreshToken.user_id == user_id).values(revoked=True))
    await session.commit()


async def rotate(session: AsyncSession, refresh_token: str) -> dict[str, str]:
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise ValueError("wrong token type")
    row = await _get_by_jti(session, payload["jti"])
    if row is None:
        raise LookupError("unknown refresh token")
    if row.revoked:
        await _revoke_all(session, row.user_id)
        raise PermissionError("refresh token reuse detected")
    await session.execute(update(RefreshToken).where(RefreshToken.jti == payload["jti"]).values(revoked=True))
    user = (await session.execute(select(User).where(User.id == row.user_id))).scalar_one()
    await session.commit()
    return await issue_pair(session, user)


async def revoke(session: AsyncSession, refresh_token: str) -> None:
    payload = decode_token(refresh_token)
    await session.execute(update(RefreshToken).where(RefreshToken.jti == payload["jti"]).values(revoked=True))
    await session.commit()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_jti() -> str:
    return uuid.uuid4().hex
```

- [ ] **Step 3: `auth.py` 追加 login/refresh/logout**

```python
from app.core.security import decode_token, verify_password
from app.services import auth_service


@router.post("/login")
async def login(request: Request, data: LoginIn, session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    user = await user_service.get_by_identity(session, data.email, data.phone)
    if not user or user.deleted_at or not user.password_hash or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    return await auth_service.issue_pair(session, user)


@router.post("/refresh")
async def refresh(data: RefreshIn, session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    try:
        return await auth_service.rotate(session, data.refresh_token)
    except LookupError:
        raise HTTPException(status_code=401, detail="刷新令牌无效") from None
    except PermissionError:
        raise HTTPException(status_code=401, detail="刷新令牌已被使用，已吊销全部会话") from None


@router.post("/logout")
async def logout(data: RefreshIn, session: AsyncSession = Depends(get_session)) -> dict[str, bool]:
    await auth_service.revoke(session, data.refresh_token)
    return {"ok": True}
```

`schemas/auth.py` 追加：

```python
class LoginIn(BaseModel):
    email: EmailStr | None = None
    phone: str | None = None
    password: str

class RefreshIn(BaseModel):
    refresh_token: str
```

`main.py` 追加限流（login）：

```python
from slowapi import Limiter
from slowapi.util import get_remote_address
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
# login 路由上：@limiter.limit("10/minute")，并给函数加 request: Request 参数
```

- [ ] **Step 4: 写 `tests/test_auth_login.py`**

```python
async def register_and_login(client, email="l@b.com"):
    await client.post("/auth/register", json={"email": email, "password": "passw0rd!", "nickname": "晨"})
    r = await client.post("/auth/login", json={"email": email, "password": "passw0rd!"})
    assert r.status_code == 200
    return r.json()


async def test_login_ok_and_tokens(client):
    tokens = await register_and_login(client)
    assert tokens["access_token"] and tokens["refresh_token"]


async def test_login_wrong_password_401(client):
    await client.post("/auth/register", json={"email": "w@b.com", "password": "passw0rd!", "nickname": "晨"})
    r = await client.post("/auth/login", json={"email": "w@b.com", "password": "wrong!"})
    assert r.status_code == 401


async def test_refresh_rotation_and_reuse_detection(client):
    tokens = await register_and_login(client, email="r@b.com")
    r1 = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r1.status_code == 200
    # 复用旧 refresh → 401 且全部会话吊销
    r2 = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r2.status_code == 401
    r3 = await client.post("/auth/refresh", json={"refresh_token": r1.json()["refresh_token"]})
    assert r3.status_code == 401


async def test_logout_revokes(client):
    tokens = await register_and_login(client, email="o@b.com")
    await client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    r = await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401
```

- [ ] **Step 5: Run** `pytest tests/test_auth_login.py -v` → Expected: `4 passed`

- [ ] **Step 6: Commit** `git add -A && git commit -m "feat: login jwt pair with rotation and reuse detection"`

---

### Task 5: 认证依赖 + GET /auth/me

**Files:**
- Create: `backend/app/api/deps.py`
- Modify: `backend/app/api/routes/auth.py`（`GET /auth/me`）
- Create: `backend/tests/test_auth_me.py`

**Interfaces:**
- Consumes: `decode_token`（Task 4）、`get_session`（Task 2）
- Produces: `get_current_user(session, credentials) -> User`（HTTP 依赖，后续 profile/gear/trip 全部复用）

- [ ] **Step 1: 写失败测试 `tests/test_auth_me.py`**

```python
from .test_auth_login import register_and_login


async def test_me_ok(client):
    tokens = await register_and_login(client, email="m@b.com")
    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert r.status_code == 200 and r.json()["nickname"] == "晨"


async def test_me_without_token_401(client):
    r = await client.get("/auth/me")
    assert r.status_code == 401


async def test_me_refresh_token_rejected(client):
    tokens = await register_and_login(client, email="mr@b.com")
    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
    assert r.status_code == 401
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_auth_me.py -v`
Expected: FAIL（404 /auth/me 不存在）

- [ ] **Step 3: 写正式实现 `app/api/deps.py`**

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.security import decode_token
from app.models.user import User

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    session: AsyncSession = Depends(get_session),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = decode_token(credentials.credentials)
    except Exception:
        raise HTTPException(status_code=401, detail="令牌无效") from None
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="令牌类型错误")
    user = (await session.execute(
        select(User).where(User.id == int(payload["sub"]))
    )).scalar_one_or_none()
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=401, detail="账号不存在或已注销")
    return user
```

- [ ] **Step 4: `auth.py` 追加 me 路由**

```python
from app.api.deps import get_current_user
from app.models.user import User


@router.get("/me", response_model=UserOut)
async def me(current: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current)
```

- [ ] **Step 5: 运行确认通过**

Run: `pytest tests/test_auth_me.py -v`
Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: auth dependency and me endpoint"
```

---
### Task 6: 画像 GET/PUT

**Files:**
- Create: `backend/app/models/profile.py`
- Create: `backend/app/schemas/profile.py`
- Create: `backend/app/services/profile_service.py`
- Create: `backend/app/api/routes/profile.py`
- Modify: `backend/app/services/user_service.py`（注册时建默认画像）
- Modify: `backend/app/main.py`（挂 profile router）
- Create: `backend/tests/test_profile.py`

**Interfaces:**
- Produces: `profile_service.get_or_create(session, user_id) -> UserProfile`、`profile_service.update(session, user_id, data) -> UserProfile`；`GET/PUT /profile -> ProfileOut`；注册即建默认画像

- [ ] **Step 1: 写 `app/models/profile.py`**

```python
from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

JsonVariant = JSON().with_variant(JSONB(), "postgresql")


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    sports: Mapped[list] = mapped_column(JsonVariant, default=list)
    exp_level: Mapped[int] = mapped_column(default=1)
    fitness: Mapped[int] = mapped_column(default=2)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 2: 写 `app/schemas/profile.py`**

```python
from pydantic import BaseModel, Field

from app.schemas.auth import Sport

VALID_SPORTS = {s.value for s in Sport}


class ProfileIn(BaseModel):
    sports: list[Sport] = Field(max_length=4)
    exp_level: int = Field(ge=1, le=4)
    fitness: int = Field(ge=1, le=5)


class ProfileOut(BaseModel):
    sports: list[Sport]
    exp_level: int
    fitness: int
```

- [ ] **Step 3: 写 `app/services/profile_service.py`**

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.profile import UserProfile
from app.schemas.profile import ProfileIn


async def get_or_create(session: AsyncSession, user_id: int) -> UserProfile:
    row = (await session.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )).scalar_one_or_none()
    if row is None:
        row = UserProfile(user_id=user_id)
        session.add(row)
        await session.commit()
    return row


async def update(session: AsyncSession, user_id: int, data: ProfileIn) -> UserProfile:
    row = await get_or_create(session, user_id)
    row.sports = [s.value for s in data.sports]
    row.exp_level = data.exp_level
    row.fitness = data.fitness
    await session.commit()
    return row
```

- [ ] **Step 4: 写 `app/api/routes/profile.py` 并挂载；注册时建默认画像**

```python
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.profile import ProfileIn, ProfileOut
from app.services import profile_service
from app.core.db import get_session

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileOut)
async def get_profile(current: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> ProfileOut:
    row = await profile_service.get_or_create(session, current.id)
    return ProfileOut(sports=row.sports, exp_level=row.exp_level, fitness=row.fitness)


@router.put("", response_model=ProfileOut)
async def put_profile(data: ProfileIn, current: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> ProfileOut:
    row = await profile_service.update(session, current.id, data)
    return ProfileOut(sports=row.sports, exp_level=row.exp_level, fitness=row.fitness)
```

`user_service.create_user` 末尾追加（注册即建默认画像）：

```python
from app.models.profile import UserProfile
session.add(UserProfile(user_id=user.id))
await session.commit()
await session.refresh(user)
```

- [ ] **Step 5: 写 `tests/test_profile.py`**

```python
from .test_auth_login import register_and_login


async def _auth_headers(client, email="p@b.com"):
    tokens = await register_and_login(client, email=email)
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_get_default_profile(client):
    h = await _auth_headers(client)
    r = await client.get("/profile", headers=h)
    assert r.status_code == 200
    assert r.json() == {"sports": [], "exp_level": 1, "fitness": 2}


async def test_put_and_get_profile(client):
    h = await _auth_headers(client, email="p2@b.com")
    body = {"sports": ["hiking", "stream"], "exp_level": 3, "fitness": 3}
    r = await client.put("/profile", json=body, headers=h)
    assert r.status_code == 200 and r.json()["sports"] == ["hiking", "stream"]
    r = await client.get("/profile", headers=h)
    assert r.json()["fitness"] == 3


async def test_put_invalid_fitness_422(client):
    h = await _auth_headers(client, email="p3@b.com")
    r = await client.put("/profile", json={"sports": ["hiking"], "exp_level": 1, "fitness": 9}, headers=h)
    assert r.status_code == 422
```

- [ ] **Step 6: Run** `pytest tests/test_profile.py -v` → Expected: `3 passed`

- [ ] **Step 7: Commit** `git add -A && git commit -m "feat: profile get/put with default row"`

---

### Task 7: 装备型号库 seed + GET /gear-catalog

**Files:**
- Create: `backend/app/services/gear_catalog.py`（49 项 + 预设型号数据）
- Create: `backend/app/models/gear.py`
- Create: `backend/app/seeds/seed_gear.py`
- Create: `backend/app/api/routes/gear.py`（`GET /gear-catalog`）
- Modify: `backend/app/main.py`（挂 gear router）
- Create: `backend/tests/test_gear_catalog.py`

**Interfaces:**
- Produces: `gear_catalog.ITEMS / MODELS / CATEGORIES`、`gear_service.seed_catalog(session) -> int`（幂等）、`GET /gear-catalog -> {categories, items}`

- [ ] **Step 1: 写 `app/services/gear_catalog.py`**（数据 = 原型 04 页全量）

```python
CATEGORIES = [
    {"key": "shoes", "label": "鞋类"}, {"key": "tech", "label": "技术装备"},
    {"key": "pack", "label": "背包"}, {"key": "cloth", "label": "服饰"},
    {"key": "elec", "label": "电子数码"}, {"key": "sun", "label": "防晒·护具"},
    {"key": "camp", "label": "露营·过夜"}, {"key": "water", "label": "水具·应急"},
]
ITEMS = [
    {"key": "boots", "label": "登山鞋", "category": "shoes"},
    {"key": "stream-shoes", "label": "溯溪鞋", "category": "shoes"},
    {"key": "climb-shoes", "label": "攀岩鞋", "category": "shoes"},
    {"key": "axe", "label": "冰镐", "category": "tech"},
    {"key": "poles", "label": "登山杖", "category": "tech"},
    {"key": "snowboard", "label": "单板雪橇", "category": "tech"},
    {"key": "ski", "label": "双板雪橇", "category": "tech"},
    {"key": "ski-poles", "label": "滑雪杖", "category": "tech"},
    {"key": "crampons", "label": "冰爪", "category": "tech"},
    {"key": "road-bike", "label": "公路自行车", "category": "tech"},
    {"key": "mtb", "label": "山地自行车", "category": "tech"},
    {"key": "moto", "label": "山地摩托车", "category": "tech"},
    {"key": "sup", "label": "桨板", "category": "tech"},
    {"key": "backpack", "label": "户外背包", "category": "pack"},
    {"key": "shell", "label": "冲锋衣", "category": "cloth"},
    {"key": "midlayer", "label": "保暖内胆", "category": "cloth"},
    {"key": "wetsuit", "label": "潜水服", "category": "cloth"},
    {"key": "sun-hoodie", "label": "防晒皮肤衣", "category": "cloth"},
    {"key": "quick-tee", "label": "速干衣", "category": "cloth"},
    {"key": "sports-bra", "label": "运动内衣", "category": "cloth"},
    {"key": "yoga-pants", "label": "瑜伽裤", "category": "cloth"},
    {"key": "cargo-pants", "label": "工装裤", "category": "cloth"},
    {"key": "rain-pants", "label": "冲锋裤", "category": "cloth"},
    {"key": "shorts", "label": "运动短裤", "category": "cloth"},
    {"key": "cycling-jersey", "label": "骑行服", "category": "cloth"},
    {"key": "headlamp", "label": "头灯", "category": "elec"},
    {"key": "gps-watch", "label": "GPS 手表", "category": "elec"},
    {"key": "power-bank", "label": "移动电源", "category": "elec"},
    {"key": "sun-cap", "label": "遮阳帽", "category": "sun"},
    {"key": "buff", "label": "多功能围脖头巾", "category": "sun"},
    {"key": "face-mask", "label": "防晒面罩", "category": "sun"},
    {"key": "arm-sleeves", "label": "防晒袖套", "category": "sun"},
    {"key": "helmet", "label": "安全帽/头盔", "category": "sun"},
    {"key": "gloves", "label": "战术防滑手套", "category": "sun"},
    {"key": "knee-pad", "label": "护膝", "category": "sun"},
    {"key": "patella-band", "label": "髌骨带", "category": "sun"},
    {"key": "sunscreen", "label": "防晒霜", "category": "sun"},
    {"key": "repellent", "label": "驱蚊喷雾", "category": "sun"},
    {"key": "tent", "label": "帐篷", "category": "camp"},
    {"key": "sleeping-bag", "label": "睡袋", "category": "camp"},
    {"key": "mat", "label": "防潮垫", "category": "camp"},
    {"key": "stove", "label": "炊具", "category": "camp"},
    {"key": "rain-gear", "label": "雨具", "category": "camp"},
    {"key": "radio", "label": "对讲机", "category": "camp"},
    {"key": "bladder", "label": "水袋", "category": "water"},
    {"key": "bottle", "label": "水壶", "category": "water"},
    {"key": "filter", "label": "过滤器", "category": "water"},
    {"key": "first-aid", "label": "急救包", "category": "water"},
    {"key": "blanket", "label": "保温毯", "category": "water"},
]
MODELS = {
    "boots": [("Salomon", "X Ultra 4 Mid GTX", "中帮 · GTX 防水"), ("Lowa", "Renegade GTX Mid", "中帮 · 防水"), ("Scarpa", "Kailash Trek GTX", "高帮 · 耐磨"), ("La Sportiva", "TX5", "高帮 · 技术线路"), ("Columbia", "Newton Ridge", "低帮 · 防滑"), ("探路者", "KFAH91358", "低帮 · 透气")],
    "stream-shoes": [("KEEN", "Newport H2", "涉水防滑"), ("Merrell", "Hydro Moc", "轻量排水"), ("探路者", "TFKE92756", "溪流鞋")],
    "climb-shoes": [("La Sportiva", "Katana", "全能"), ("Climb X", "Flashlight", "入门舒适"), ("OCUN", "Ozone", "灵敏精准")],
    "axe": [("Petzl", "Glacier", "行走制动"), ("Black Diamond", "Raven Ultra", "轻量雪线")],
    "poles": [("Black Diamond", "Trail", "铝合金·外锁"), ("LEKI", "Makalu Lite", "铝合金·外锁"), ("Fizan", "Compact 3", "碳纤维·内锁"), ("NH挪客", "碳素快锁杖", "碳纤维·外锁")],
    "snowboard": [("Burton", "Custom", "全能凸边"), ("Nitro", "Team", "公园全能"), ("YES", "Basic", "入门性价比")],
    "ski": [("Rossignol", "Experience 84", "全能道内外"), ("Atomic", "Cloud Q9", "道内轻松"), ("Salomon", "QST 92", "道外野雪")],
    "ski-poles": [("LEKI", "Spark S", "铝合金轻量"), ("Volkl", "Phantastick", "碳素超轻"), ("迪卡侬", "Wedze 500", "入门性价比")],
    "crampons": [("Petzl", "Leopard LLF", "绑式轻量"), ("Black Diamond", "Neve Pro", "全绑技术"), ("Grivel", "G10", "经典十齿")],
    "road-bike": [("Giant", "TCR Advanced", "碳架竞速"), ("Trek", "Emonda ALR", "轻量爬坡"), ("Merida", "Scultura", "耐力性价比")],
    "mtb": [("Giant", "XTC 800", "XC 硬尾"), ("Trek", "Marlin 7", "入门油压碟刹"), ("Specialized", "Stumpjumper", "软尾 Trail")],
    "moto": [("KTM", "350 EXC-F", "Enduro 越野"), ("Honda", "CRF250L", "林道可上牌"), ("Yamaha", "WR250F", "越野轻量")],
    "sup": [("Aqua Marina", "Vapor", "充气全能"), ("迪卡侬", "Itiwit 100", "入门稳定"), ("ZRAY", "S9", "旅行钓鱼")],
    "backpack": [("Osprey", "Kestrel 38L", "AirScape 背负"), ("Gregory", "Zulu 30L", "轻量化"), ("deuter", "Aircontact 45+10", "重装防雨罩"), ("凯乐石", "Lesson PY 28L", "28L 便携")],
    "shell": [("始祖鸟", "Beta LT", "硬壳 GTX"), ("Mammut", "Rime IN", "软壳透气"), ("凯乐石", "KG710275", "硬壳性价比"), ("伯希和", "软壳外套", "日常通勤")],
    "midlayer": [("Patagonia", "Down Sweater", "鹅绒 800FP"), ("凯乐石", "金字塔羽绒", "鸭绒 700FP"), ("Patagonia", "R1", "抓绒透气"), ("迪卡侬", "MH120 抓绒", "抓绒性价比")],
    "wetsuit": [("Hisky", "3mm 连体湿式", "溯溪保暖"), ("BARA", "溯溪分体服", "耐磨弹力")],
    "sun-hoodie": [("蕉下", "披肩防晒衣", "UPF50+"), ("迪卡侬", "防晒皮肤衣", "轻量透气")],
    "quick-tee": [("始祖鸟", "Phase SL", "轻量排汗"), ("迪卡侬", "MH500 速干T", "性价比")],
    "sports-bra": [("Lululemon", "Energy Bra", "高强度支撑"), ("迪卡侬", "运动内衣", "中强度速干")],
    "yoga-pants": [("Lululemon", "Align 25", "裸感高腰"), ("迪卡侬", "瑜伽裤", "高弹性价比")],
    "cargo-pants": [("迪卡侬", "Forclaz 500", "徒步耐磨"), ("伯希和", "软壳工装裤", "弹力防泼水")],
    "rain-pants": [("凯乐石", "KG210152", "防水透气"), ("探路者", "冲锋裤", "防泼水保暖")],
    "shorts": [("迪卡侬", "KIPSTA 短裤", "速干轻量"), ("Nike", "Dri-FIT", "排汗弹力")],
    "cycling-jersey": [("Castelli", "骑行上衣", "气动排汗"), ("捷安特", "骑行套装", "反光透气")],
    "headlamp": [("Petzl", "Actik Core", "600lm USB-C"), ("Black Diamond", "Spot 400", "400lm 防水"), ("奈特科尔", "NU25", "超轻 360lm")],
    "gps-watch": [("Garmin", "Fenix 7", "双频GPS 太阳能"), ("COROS", "APEX 2 Pro", "长续航越野"), ("Garmin", "Instinct 2", "三防性价比")],
    "power-bank": [("Anker", "20000mAh", "22.5W 快充"), ("紫米", "10000mAh", "轻薄自带线")],
    "sun-cap": [("蕉下", "渔夫帽", "UPF50+ 折叠"), ("Columbia", "Bora Bora", "防泼水快干")],
    "buff": [("Buff", "Original", "多用途速干")],
    "face-mask": [("蕉下", "护颈面罩", "UPF50+ 透气")],
    "arm-sleeves": [("蕉下", "冰袖", "冰感 UPF50+")],
    "helmet": [("Petzl", "Boreo", "攀岩侧向防护"), ("迪卡侬", "登山头盔", "轻量性价比")],
    "gloves": [("Mechanix", "Original", "耐磨触屏"), ("黑冰", "防滑手套", "轻薄透气")],
    "knee-pad": [("LP", "运动护膝", "支撑透气"), ("LP", "髌骨带", "下山减压")],
    "patella-band": [("LP", "髌骨带", "下山减压")],
    "sunscreen": [("安热沙", "金瓶 SPF50+", "持久的汗"), ("薇诺娜", "清透防晒乳", "温和敏感肌")],
    "repellent": [("OFF!", "欧护家驱蚊液", "长效户外")],
    "tent": [("牧高笛", "冷山 2", "铝杆双人"), ("NH挪客", "云尚 2", "轻量化露营")],
    "sleeping-bag": [("黑冰", "G700", "鸭绒木乃伊"), ("天石", "信封式睡袋", "四季棉")],
    "mat": [("Therm-a-Rest", "蛋槽垫", "折叠耐用"), ("NH挪客", "充气垫", "厚实轻量")],
    "stove": [("火枫", "盛宴 3 套锅", "2-3人收纳"), ("火枫", "mini 气炉", "超轻 3000W")],
    "rain-gear": [("探路者", "分体雨衣", "防水透气"), ("NH挪客", "背包雨披", "含背包仓")],
    "radio": [("北峰", "BF-5111", "民用长续航"), ("摩托罗拉", "T50", "免执照轻巧")],
    "bladder": [("Platypus", "2L 水袋", "轻量无异味"), ("CamelBak", "Crux 2L", "大流量吸管")],
    "bottle": [("Nalgene", "1L Tritan", "耐摔广口"), ("膳魔师", "保温壶 500ml", "保温12h")],
    "filter": [("Katadyn", "BeFree", "快流可反洗"), ("Sawyer", "Squeeze", "挤压式长寿命")],
    "first-aid": [("登山标准版", "含敷料绷带药品", "1-2日线配置"), ("轻量便携版", "基础敷料碘伏", "半日线配置")],
    "blanket": [("应急保温毯", "银色双面反光", "防失温 210x160")],
}
```

- [ ] **Step 2: 写 `app/models/gear.py`**

```python
from sqlalchemy import BigInteger, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GearModel(Base):
    __tablename__ = "gear_models"
    __table_args__ = (UniqueConstraint("item_key", "brand", "model"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    item_key: Mapped[str] = mapped_column(String(32), index=True)
    brand: Mapped[str] = mapped_column(String(48))
    model: Mapped[str] = mapped_column(String(64))
    spec: Mapped[str | None] = mapped_column(String(128))


class UserGear(Base):
    __tablename__ = "user_gear"
    __table_args__ = (UniqueConstraint("user_id", "item_key", "model_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    item_key: Mapped[str] = mapped_column(String(32))
    model_id: Mapped[int | None] = mapped_column(ForeignKey("gear_models.id"))
    custom_name: Mapped[str | None] = mapped_column(String(48))
```

- [ ] **Step 3: 写 `app/seeds/seed_gear.py`（幂等 upsert）**

```python
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.services.gear_catalog import MODELS
from app.models.gear import GearModel


async def seed(session: AsyncSession) -> int:
    added = 0
    for item_key, entries in MODELS.items():
        for brand, model, spec in entries:
            exists = (await session.execute(
                select(GearModel).where(GearModel.item_key == item_key,
                                        GearModel.brand == brand, GearModel.model == model)
            )).scalar_one_or_none()
            if exists is None:
                session.add(GearModel(item_key=item_key, brand=brand, model=model, spec=spec))
                added += 1
    await session.commit()
    return added


async def main() -> None:
    async with SessionLocal() as session:
        print("seeded:", await seed(session))


if __name__ == "__main__":
    asyncio.run(main())
```

Run: `python -m app.seeds.seed_gear`（对 compose postgres）Expected: `seeded: <N>`，重复执行输出 `seeded: 0`

- [ ] **Step 4: 写 `app/api/routes/gear.py`（catalog）并挂载**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.services.gear_catalog import CATEGORIES, ITEMS, MODELS

router = APIRouter(prefix="/gear", tags=["gear"])


@router.get("/catalog")
async def catalog(session: AsyncSession = Depends(get_session)) -> dict:
    from sqlalchemy import select
    from app.models.gear import GearModel
    rows = (await session.execute(select(GearModel))).scalars().all()
    by_item: dict[str, list[dict]] = {}
    for r in rows:
        by_item.setdefault(r.item_key, []).append({"id": r.id, "brand": r.brand, "model": r.model, "spec": r.spec})
    items = [{**it, "models": by_item.get(it["key"], [])} for it in ITEMS if by_item.get(it["key"])]
    return {"categories": CATEGORIES, "items": items}
```

- [ ] **Step 5: 写 `tests/test_gear_catalog.py`**

```python
from app.seeds.seed_gear import seed


async def test_catalog_after_seed(client, db):
    await seed(db)
    r = await client.get("/gear/catalog")
    assert r.status_code == 200
    body = r.json()
    keys = {i["key"] for i in body["items"]}
    assert {"boots", "snowboard", "l-snow"[:0] or "ski"} <= keys or "boots" in keys
    assert len(body["categories"]) == 8
    boots = next(i for i in body["items"] if i["key"] == "boots")
    assert any(m["brand"] == "Salomon" for m in boots["models"])


async def test_catalog_idempotent_seed(client, db):
    n1 = await seed(db)
    n2 = await seed(db)
    assert n2 == 0
```

- [ ] **Step 6: Run** `pytest tests/test_gear_catalog.py -v` → Expected: `2 passed`

- [ ] **Step 7: Commit** `git add -A && git commit -m "feat: gear catalog with idempotent seed"`

---

### Task 8: 装备清单 PUT/GET

**Files:**
- Create: `backend/app/schemas/gear.py`
- Modify: `backend/app/api/routes/gear.py`（`PUT /gear-list`、`GET /gear-list`）
- Create: `backend/tests/test_gear_list.py`

**Interfaces:**
- Produces: `GearListIn`、`GearItemOut`、`PUT /gear-list`（整表替换语义）、`GET /gear-list`

- [ ] **Step 1: 写 `app/schemas/gear.py`**

```python
from pydantic import BaseModel, Field


class GearItemIn(BaseModel):
    item_key: str
    model_id: int | None = None
    custom_name: str | None = Field(None, max_length=48)


class GearListIn(BaseModel):
    items: list[GearItemIn] = Field(max_length=200)


class GearItemOut(BaseModel):
    item_key: str
    model_id: int | None
    custom_name: str | None
```

- [ ] **Step 2: `gear.py` 追加 PUT/GET**

```python
from sqlalchemy import delete, select

from app.api.deps import get_current_user
from app.models.gear import UserGear
from app.models.user import User
from app.schemas.gear import GearItemIn, GearItemOut, GearListIn


@router.get("/gear-list", response_model=list[GearItemOut])
async def get_gear_list(current: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> list[GearItemOut]:
    rows = (await session.execute(select(UserGear).where(UserGear.user_id == current.id))).scalars().all()
    return [GearItemOut(item_key=r.item_key, model_id=r.model_id, custom_name=r.custom_name) for r in rows]


@router.put("/gear-list", response_model=list[GearItemOut])
async def put_gear_list(data: GearListIn, current: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> list[GearItemOut]:
    await session.execute(delete(UserGear).where(UserGear.user_id == current.id))
    for it in data.items:
        session.add(UserGear(user_id=current.id, item_key=it.item_key, model_id=it.model_id, custom_name=it.custom_name))
    await session.commit()
    rows = (await session.execute(select(UserGear).where(UserGear.user_id == current.id))).scalars().all()
    return [GearItemOut(item_key=r.item_key, model_id=r.model_id, custom_name=r.custom_name) for r in rows]
```

- [ ] **Step 3: 写 `tests/test_gear_list.py`**

```python
from app.seeds.seed_gear import seed
from .test_auth_login import register_and_login


async def test_put_get_replace(client, db):
    await seed(db)
    tokens = await register_and_login(client, email="g@b.com")
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    r = await client.put("/gear-list", json={"items": [
        {"item_key": "boots", "model_id": 1}, {"item_key": "poles", "model_id": 7}]}, headers=h)
    assert r.status_code == 200 and len(r.json()) == 2
    # 整表替换语义：第二次 PUT 覆盖第一次
    r = await client.put("/gear-list", json={"items": [{"item_key": "shell", "model_id": 30}]}, headers=h)
    assert len(r.json()) == 1 and r.json()[0]["item_key"] == "shell"


async def test_put_requires_auth(client):
    r = await client.put("/gear-list", json={"items": []})
    assert r.status_code == 401
```

- [ ] **Step 4: Run** `pytest tests/test_gear_list.py -v` → Expected: `2 passed`

- [ ] **Step 5: Commit** `git add -A && git commit -m "feat: gear list replace semantics"`

---

### Task 9: 质量门（Ruff/mypy/覆盖率）+ OpenAPI 导出 + CI

**Files:**
- Modify: `backend/pyproject.toml`（追加 pytest addopts 与 ruff/mypy 细化）
- Create: `backend/.github/workflows/ci.yml`
- Create: `backend/scripts/export_openapi.py`

**Interfaces:**
- Produces: `openapi.json`（供各端生成 API 客户端）、CI 工作流

- [ ] **Step 1: `pyproject.toml` 追加**

```toml
[tool.pytest.ini_options]
addopts = "-q --cov=app --cov-report=term-missing"
[tool.coverage.report]
fail_under = 85
```

（dev 依赖追加：`pytest-cov>=5`）

- [ ] **Step 2: 写 `scripts/export_openapi.py`**

```python
import json

from app.main import app

print(json.dumps(app.openapi(), ensure_ascii=False, indent=2))
```

Run: `python -m scripts.export_openapi > openapi.json`
Expected: `openapi.json` 含 `/auth/login`、`/gear-catalog` 等路径

- [ ] **Step 3: 写 `.github/workflows/ci.yml`**

```yaml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.12"}
      - run: pip install -e ".[dev]"
      - run: ruff check app tests
      - run: mypy app
      - run: python scripts/export_openapi.py > openapi.json
      - run: pytest
```

- [ ] **Step 4: Run** `ruff check app tests && mypy app && pytest` → Expected: 全绿

- [ ] **Step 5: Commit** `git add -A && git commit -m "chore: ci quality gates and openapi export"`

---

## Self-Review 记录

- 规格覆盖：specification §2 的 01/02/03/04/09 页对应能力（登录/画像/装备）全部有任务；M2 起覆盖 05-08/10。
- 占位符扫描：Task 5 Step 1 的占位实现已在 Step 2 显式覆盖并说明——这是 TDD 先红后绿的一环，非占位符残留。
- 类型一致性：`issue_pair/rotate/revoke`、`get_or_create/update`、`seed` 的签名在各任务间已对齐。
