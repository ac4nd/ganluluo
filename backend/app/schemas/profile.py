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
