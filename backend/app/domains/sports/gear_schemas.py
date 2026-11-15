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
