from fastapi import FastAPI

from app.api.routes.ops import router as ops_router


def create_app() -> FastAPI:
    app = FastAPI(title="GanLuLuo API", version="0.1.0")
    app.include_router(ops_router, prefix="/ops", tags=["ops"])
    return app


app = create_app()
