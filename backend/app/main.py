from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import Response


def rate_limit_exceeded_handler(request: Request, exc: Exception) -> Response:
    # Starlette's handler registry types exc as Exception, while slowapi's handler
    # is typed for RateLimitExceeded; only that class is registered, so narrow first.
    assert isinstance(exc, RateLimitExceeded)
    return _rate_limit_exceeded_handler(request, exc)

# Defined before router imports: app.api.routes.auth imports this limiter
# for the @limiter.limit decorator on /auth/login (avoids circular import).
limiter = Limiter(key_func=get_remote_address)

from app.agent.memory_router import router as memory_router
from app.agent.router import router as assistant_router
from app.api.routes.ops import router as ops_router
from app.domains.auth.router import router as auth_router
from app.domains.sports.gear_router import router as gear_router
from app.domains.sports.profile_router import router as profile_router
from app.domains.sports.route_router import router as routes_router


def create_app() -> FastAPI:
    app = FastAPI(title="GanLuLuo API", version="0.1.0")
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.include_router(ops_router, prefix="/ops", tags=["ops"])
    app.include_router(assistant_router, prefix="/assistant", tags=["assistant"])
    app.include_router(memory_router, prefix="/assistant", tags=["assistant"])
    app.include_router(auth_router, tags=["auth"])
    app.include_router(profile_router, tags=["profile"])
    app.include_router(gear_router)
    app.include_router(routes_router)
    return app


app = create_app()
