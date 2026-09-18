from pydantic import BaseModel, Field


class TierIn(BaseModel):
    # None means the open-ended last band.
    up_to: float | None = None
    price: float


class DraftSaveRequest(BaseModel):
    tiers: list[TierIn] = Field(min_length=1)


class ProbeRequest(BaseModel):
    """A probe meter reading used for draft trial / before-vs-after comparison."""

    kwh: float = Field(ge=0)
    peak: bool = False
