from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# Defined before router imports: app.api.routes.auth imports this limiter
# for the @limiter.limit decorator on /auth/login (avoids circular import).
limiter = Limiter(key_func=get_remote_address)

from app.api.routes.auth import router as auth_router
from app.api.routes.gear import router as gear_router
from app.api.routes.ops import router as ops_router
from app.api.routes.profile import router as profile_router


def create_app() -> FastAPI:
    app = FastAPI(title="GanLuLuo API", version="0.1.0")
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(ops_router, prefix="/ops", tags=["ops"])
    app.include_router(auth_router, tags=["auth"])
    app.include_router(profile_router, tags=["profile"])
    app.include_router(gear_router)
    return app


app = create_app()
