from fastapi import APIRouter, HTTPException

from app.engines.tier_progressive import TierValidationError
from app.schemas.tiers import DraftSaveRequest, ProbeRequest
from app.services.billing_service import BillingService, DraftMissingError

router = APIRouter(tags=["tiers"])


@router.get("/tiers")
def list_tiers():
    with BillingService() as svc:
        return {"items": svc.list_tiers()}


@router.get("/tiers/draft")
def get_draft():
    """Both the unapplied draft (may be null) and the active ladder."""
    with BillingService() as svc:
        return svc.get_draft()


@router.put("/tiers/draft")
def save_draft(body: DraftSaveRequest):
    with BillingService() as svc:
        return svc.save_draft([t.model_dump() for t in body.tiers])


def _draft_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DraftMissingError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, TierValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    raise exc


@router.post("/tiers/draft/trial")
def trial_draft(body: ProbeRequest):
    """Read-only trial against the draft; active tiers and run history untouched."""
    with BillingService() as svc:
        try:
            return svc.trial_draft(body.kwh, body.peak)
        except (DraftMissingError, TierValidationError) as e:
            raise _draft_error(e)


@router.post("/tiers/draft/preview")
def preview_apply(body: ProbeRequest):
    """Before/after segment comparison without replacing the active ladder."""
    with BillingService() as svc:
        try:
            return svc.preview_apply(body.kwh, body.peak)
        except (DraftMissingError, TierValidationError) as e:
            raise _draft_error(e)


@router.post("/tiers/draft/apply")
def apply_draft(body: ProbeRequest):
    """Validate then atomically replace the active ladder; returns before/after."""
    with BillingService() as svc:
        try:
            return svc.apply_draft(body.kwh, body.peak)
        except (DraftMissingError, TierValidationError) as e:
            raise _draft_error(e)
