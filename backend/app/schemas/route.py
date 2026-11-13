from pydantic import BaseModel, Field

from app.schemas.auth import Sport


class RouteIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    region: str = Field(min_length=1, max_length=64)
    sport: Sport
    difficulty: int = Field(ge=1, le=5)
    distance_km: float = Field(gt=0)
    climb_m: int = Field(ge=0)
    duration_h: float | None = None
    clarity: str = "mid"
    start_lat: float | None = None
    start_lon: float | None = None
    required_gear: list[str] = []


class RouteOut(BaseModel):
    id: int
    name: str
    region: str
    sport: Sport
    difficulty: int
    distance_km: float
    climb_m: int
    duration_h: float | None
    clarity: str
    model_config = {"from_attributes": True}


class RouteDetailOut(RouteOut):
    elevation: list[dict]
    pace: list[dict]
    terrain: list[dict]
    required_gear: list[str]
    warning: str | None


class TrackSummaryOut(BaseModel):
    points: int
    distance_km: float
    climb_m: int
    difficulty: int
    clarity: str
