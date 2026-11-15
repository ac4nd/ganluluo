from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from starlette.responses import Response

# limiter 定义在 core（M6.5 I-6 抽出）：auth/assistant/media router 直接从
# app.core.rate_limit import，app.main 不再是 limiter 的家（循环导入债已清）。
from app.core.rate_limit import limiter


def rate_limit_exceeded_handler(request: Request, exc: Exception) -> Response:
    # Starlette's handler registry types exc as Exception, while slowapi's handler
    # is typed for RateLimitExceeded; only that class is registered, so narrow first.
    assert isinstance(exc, RateLimitExceeded)
    return _rate_limit_exceeded_handler(request, exc)

from app.api.routes.ops import router as ops_router
from app.assistant.memory_router import router as memory_router
from app.assistant.plan_router import router as plan_router
from app.assistant.router import router as assistant_router
from app.domains.admin.admin_router import router as admin_router
from app.domains.auth.router import router as auth_router
from app.domains.media.media_router import router as media_router
from app.domains.sports.gear_router import router as gear_router
from app.domains.sports.profile_router import router as profile_router
from app.domains.sports.route_router import router as routes_router
from app.domains.sports.track_router import router as tracks_router
from app.domains.sports.trip_router import router as trips_router


def create_app() -> FastAPI:
    app = FastAPI(title="GanLuLuo API", version="0.1.0")
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.include_router(ops_router, prefix="/ops", tags=["ops"])
    app.include_router(admin_router, prefix="/admin", tags=["admin"])
    app.include_router(assistant_router, prefix="/assistant", tags=["assistant"])
    app.include_router(memory_router, prefix="/assistant", tags=["assistant"])
    app.include_router(plan_router, prefix="/assistant", tags=["assistant"])
    app.include_router(trips_router, prefix="/trips", tags=["trips"])
    app.include_router(auth_router, tags=["auth"])
    app.include_router(profile_router, tags=["profile"])
    app.include_router(gear_router)
    app.include_router(routes_router)
    app.include_router(tracks_router, prefix="/tracks", tags=["tracks"])
    app.include_router(media_router, prefix="/media", tags=["media"])
    return app


app = create_app()
