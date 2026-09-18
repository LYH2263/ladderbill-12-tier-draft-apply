from pydantic import BaseModel, Field


class TierRowIn(BaseModel):
    up_to: float | None = None
    price: float


class DraftSaveRequest(BaseModel):
    items: list[TierRowIn] = Field(min_length=1)


class TierProbeRequest(BaseModel):
    kwh: float = Field(ge=0)
    peak: bool = False
