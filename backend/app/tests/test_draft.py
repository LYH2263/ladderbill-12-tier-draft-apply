import pytest

from app import seed
from app.db import connect
from app.engines.tier_progressive import (
    TierValidationError,
    calc_bill,
    validate_tiers,
)
from app.services.billing_service import BillingService, DraftMissingError


@pytest.fixture()
def db(tmp_path, monkeypatch):
    import app.db as db_mod

    db_path = tmp_path / "test.db"
    monkeypatch.setattr(db_mod, "DB_PATH", db_path)
    seed.init_db()
    yield db_path


ACTIVE_SEED = [
    {"up_to": 180, "price": 0.52},
    {"up_to": 260, "price": 0.62},
    {"up_to": None, "price": 0.82},
]
NEW_DRAFT = [
    {"up_to": 200, "price": 0.55},
    {"up_to": 300, "price": 0.65},
    {"up_to": None, "price": 0.85},
]


def _run_count() -> int:
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) c FROM calc_runs").fetchone()["c"]


def _active_rows():
    with BillingService() as svc:
        return svc.list_tiers()


# ---------- validator ----------


def test_validate_accepts_seed_shape():
    validate_tiers(ACTIVE_SEED)


def test_validate_rejects_negative_price():
    bad = [{"up_to": 180, "price": -0.1}, {"up_to": None, "price": 0.8}]
    with pytest.raises(TierValidationError):
        validate_tiers(bad)


def test_validate_rejects_non_monotonic_bounds():
    bad = [{"up_to": 260, "price": 0.6}, {"up_to": 180, "price": 0.7}, {"up_to": None, "price": 0.8}]
    with pytest.raises(TierValidationError):
        validate_tiers(bad)


def test_validate_rejects_open_end_not_last():
    bad = [{"up_to": None, "price": 0.5}, {"up_to": 260, "price": 0.7}]
    with pytest.raises(TierValidationError):
        validate_tiers(bad)


def test_validate_rejects_empty():
    with pytest.raises(TierValidationError):
        validate_tiers([])


# ---------- draft read/write ----------


def test_get_draft_initially_null_but_active_readable(db):
    with BillingService() as svc:
        payload = svc.get_draft()
    assert payload["items"] is None
    assert payload["active"] == ACTIVE_SEED


def test_save_draft_does_not_change_active(db):
    with BillingService() as svc:
        svc.save_draft(NEW_DRAFT)
    rows = _active_rows()
    assert [(r["up_to"], r["price"]) for r in rows] == [(180, 0.52), (260, 0.62), (None, 0.82)]


def test_trial_without_draft_raises(db):
    with BillingService() as svc:
        with pytest.raises(DraftMissingError):
            svc.trial_draft(400, False)


def test_trial_uses_draft_marks_source_and_persists_nothing(db):
    before_runs = _run_count()
    with BillingService() as svc:
        svc.save_draft(NEW_DRAFT)
        result = svc.trial_draft(400, False)

    assert result["source"] == "draft"
    assert result["run_id"] is None
    expected = calc_bill(400, NEW_DRAFT, 1.0)
    assert result["total"] == expected["total"]
    assert result["segments"] == expected["segments"]
    # no run history written
    assert _run_count() == before_runs
    # active ladder untouched
    with BillingService() as svc:
        assert svc.list_tiers()[0]["price"] == 0.52


def test_trial_invalid_draft_raises_and_changes_nothing(db):
    bad = [{"up_to": 300, "price": 0.6}, {"up_to": 200, "price": 0.7}, {"up_to": None, "price": 0.8}]
    with BillingService() as svc:
        svc.save_draft(bad)
        with pytest.raises(TierValidationError):
            svc.trial_draft(100, False)
    with BillingService() as svc:
        assert svc.list_tiers()[0]["price"] == 0.52


def test_preview_is_readonly_and_tags_draft_after(db):
    with BillingService() as svc:
        svc.save_draft(NEW_DRAFT)
        p = svc.preview_apply(400, False)

    assert p["applied"] is False
    assert p["before"]["source"] == "active"
    assert p["after"]["source"] == "draft"
    assert p["before"]["total"] == calc_bill(400, ACTIVE_SEED, 1.0)["total"]
    assert p["after"]["total"] == calc_bill(400, NEW_DRAFT, 1.0)["total"]
    # preview replaces nothing and keeps the draft
    with BillingService() as svc:
        assert svc.list_tiers()[0]["price"] == 0.52
        assert svc.get_draft()["items"] == NEW_DRAFT


# ---------- apply ----------


def test_apply_invalid_draft_keeps_old_active(db):
    bad = [{"up_to": 100, "price": 0.5}, {"up_to": 100, "price": -0.1}, {"up_to": None, "price": 0.9}]
    with BillingService() as svc:
        svc.save_draft(bad)
        with pytest.raises(TierValidationError):
            svc.apply_draft(400, False)
    # old active ladder intact, draft retained for further editing
    with BillingService() as svc:
        active = svc.list_tiers()
        assert [(r["up_to"], r["price"]) for r in active] == [
            (180, 0.52),
            (260, 0.62),
            (None, 0.82),
        ]
        assert svc.get_draft()["items"] == bad


def test_apply_valid_draft_replaces_active_and_returns_comparison(db):
    before_runs = _run_count()
    with BillingService() as svc:
        svc.save_draft(NEW_DRAFT)
        summary = svc.apply_draft(400, False)

    assert summary["applied"] is True
    assert summary["kwh"] == 400
    assert summary["before"]["source"] == "active"
    assert summary["after"]["source"] == "active"
    assert summary["before"]["total"] == calc_bill(400, ACTIVE_SEED, 1.0)["total"]
    assert summary["after"]["total"] == calc_bill(400, NEW_DRAFT, 1.0)["total"]
    assert summary["before"]["total"] != summary["after"]["total"]
    assert len(summary["before"]["segments"]) == 3
    assert len(summary["after"]["segments"]) == 3

    # active ladder is now the draft
    with BillingService() as svc:
        active = svc.list_tiers()
        assert [(r["up_to"], r["price"]) for r in active] == [
            (200, 0.55),
            (300, 0.65),
            (None, 0.85),
        ]
        # consumed draft is cleared
        assert svc.get_draft()["items"] is None

    # apply writes no run history
    assert _run_count() == before_runs


def test_workbench_after_apply_matches_after_summary(db):
    """The acceptance check: a normal workbench calc on the active ladder after
    apply must produce exactly the segments returned in the apply summary."""
    with BillingService() as svc:
        svc.save_draft(NEW_DRAFT)
        summary = svc.apply_draft(240, False)
        post = svc.run_bill(240, False, None, persist=False)

    assert post["segments"] == summary["after"]["segments"]
    assert post["total"] == summary["after"]["total"]
