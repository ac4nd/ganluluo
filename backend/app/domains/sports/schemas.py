from pydantic import BaseModel, Field, model_validator

from app.domains.auth.schemas import Sport


class ProfileIn(BaseModel):
    sports: list[Sport] = Field(max_length=4)
    exp_level: int = Field(ge=1, le=4)
    fitness: int = Field(ge=1, le=5)

    @model_validator(mode="after")
    def dedupe_sports(self) -> "ProfileIn":
        self.sports = list(dict.fromkeys(self.sports))
        return self


class ProfileOut(BaseModel):
    sports: list[Sport]
    exp_level: int
    fitness: int
