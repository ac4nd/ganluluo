import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db import Base, get_session
from app.main import create_app, limiter


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    # The slowapi limiter is module-level with in-memory storage keyed by the
    # TestClient IP; reset it before every test so tests stay order-independent
    # and can never trip the 10/minute limit on /auth/login.
    limiter.reset()
    yield


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
