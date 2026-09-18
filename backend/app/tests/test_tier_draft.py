import os
import tempfile

# Point the app at a throwaway DB before any app module is imported.
_TMP = tempfile.mkdtemp(prefix="ladderbill-test-")
os.environ["DATA_DIR"] = _TMP

import pytest

from app import seed
from app.db import DB_PATH, connect
from app.services.billing_service import BillingService


@pytest.fixture()
def svc():
    if DB_PATH.exists():
        DB_PATH.unlink()
    seed.init_db()
    with BillingService() as s:
        yield s


def _runs_count() -> int:
    conn = connect()
    try:
        return conn.execute("SELECT COUNT(*) c FROM calc_runs").fetchone()["c"]
    finally:
        conn.close()


def test_save_and_read_draft_alongside_official(svc):
    svc.save_draft([{"up_to": 200, "price": 0.5}, {"up_to": None, "price": 0.9}])
    d = svc.get_draft()
    assert [r["up_to"] for r in d["items"]] == [200, None]
    assert [r["price"] for r in d["items"]] == [0.5, 0.9]
    assert d["updated_at"]
    # official stays readable and untouched
    assert [t["price"] for t in svc.list_tiers()] == [0.52, 0.62, 0.82]


def test_simulate_marks_draft_source_and_writes_nothing(svc):
    svc.save_draft([{"up_to": 200, "price": 0.5}, {"up_to": None, "price": 0.9}])
    runs_before = _runs_count()
    official_before = svc.list_tiers()
    res = svc.simulate_draft(220, False)
    assert res["source"] == "draft"
    assert res["draft"]["total"] == 118.0  # 200*0.5 + 20*0.9
    assert res["official"]["total"] == 118.4  # 180*0.52 + 40*0.62
    assert res["delta_total"] == -0.4
    # no run persisted, official unchanged
    assert _runs_count() == runs_before
    assert svc.list_tiers() == official_before


def test_simulate_without_draft_raises(svc):
    with pytest.raises(LookupError):
        svc.simulate_draft(100, False)


def test_apply_replaces_official_and_returns_summary(svc):
    svc.save_draft([{"up_to": 200, "price": 0.5}, {"up_to": None, "price": 0.9}])
    res = svc.apply_draft(220, False)
    assert res["applied"] is True
    assert res["before"]["total"] == 118.4
    assert res["after"]["total"] == 118.0
    assert res["delta_total"] == -0.4
    assert [t["price"] for t in svc.list_tiers()] == [0.5, 0.9]
    # workbench consistency: billing off the new official matches the after-summary
    bill = svc.run_bill(220, False, None, persist=False)
    assert bill["segments"] == res["after"]["segments"]
    assert bill["total"] == res["after"]["total"]


def test_apply_with_peak_probe_uses_peak_factor(svc):
    svc.save_draft([{"up_to": None, "price": 1.0}])
    res = svc.apply_draft(100, True)
    assert res["before"]["total"] == 62.4  # 100*0.52*1.2
    assert res["after"]["total"] == 120.0  # 100*1.0*1.2


def test_apply_rejects_non_monotonic_bounds_and_keeps_official(svc):
    svc.save_draft(
        [
            {"up_to": 260, "price": 0.62},
            {"up_to": 180, "price": 0.52},
            {"up_to": None, "price": 0.82},
        ]
    )
    official_before = svc.list_tiers()
    with pytest.raises(ValueError):
        svc.apply_draft(220, False)
    assert svc.list_tiers() == official_before


def test_apply_rejects_negative_price_and_keeps_official(svc):
    svc.save_draft([{"up_to": 180, "price": -0.1}, {"up_to": None, "price": 0.82}])
    official_before = svc.list_tiers()
    with pytest.raises(ValueError):
        svc.apply_draft(220, False)
    assert svc.list_tiers() == official_before


def test_apply_rejects_open_tier_not_last(svc):
    svc.save_draft([{"up_to": None, "price": 0.5}, {"up_to": 300, "price": 0.9}])
    with pytest.raises(ValueError):
        svc.apply_draft(220, False)


def test_apply_without_draft_raises(svc):
    with pytest.raises(LookupError):
        svc.apply_draft(100, False)
