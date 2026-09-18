from fastapi import APIRouter, HTTPException

from app.schemas.tiers import DraftSaveRequest, TierProbeRequest
from app.services.billing_service import BillingService

router = APIRouter(tags=["tiers"])


@router.get("/tiers")
def list_tiers():
    with BillingService() as svc:
        return {"items": svc.list_tiers()}


@router.get("/tiers/draft")
def get_tier_draft():
    with BillingService() as svc:
        return svc.get_draft()


@router.put("/tiers/draft")
def save_tier_draft(body: DraftSaveRequest):
    rows = [{"up_to": r.up_to, "price": r.price} for r in body.items]
    with BillingService() as svc:
        return svc.save_draft(rows)


@router.post("/tiers/draft/simulate")
def simulate_tier_draft(body: TierProbeRequest):
    with BillingService() as svc:
        try:
            return svc.simulate_draft(body.kwh, body.peak)
        except LookupError as e:
            raise HTTPException(status_code=409, detail=str(e))


@router.post("/tiers/apply")
def apply_tier_draft(body: TierProbeRequest):
    with BillingService() as svc:
        try:
            return svc.apply_draft(body.kwh, body.peak)
        except LookupError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
