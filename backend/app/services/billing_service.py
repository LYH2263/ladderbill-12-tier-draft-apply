import json

from app.db import connect
from app.engines.peak_compare import compare_plain_vs_peak
from app.engines.tier_progressive import TierValidationError, calc_bill, validate_tiers
from app.repositories import accounts as accounts_repo
from app.repositories import readings as readings_repo
from app.repositories import runs as runs_repo
from app.repositories import settings as settings_repo
from app.repositories import tier_drafts as drafts_repo
from app.repositories import tiers as tiers_repo


class DraftMissingError(RuntimeError):
    """No draft ladder has been saved yet."""


class BillingService:
    def __init__(self):
        self._conn = connect()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def list_accounts(self):
        return accounts_repo.list_all(self._conn)

    def get_account(self, account_id: int):
        return accounts_repo.get(self._conn, account_id)

    def list_tiers(self):
        return tiers_repo.list_ordered(self._conn)

    def get_draft(self) -> dict:
        """Draft and active ladder are both readable; draft may be absent."""
        return {
            "items": drafts_repo.get_rows(self._conn),
            "active": tiers_repo.as_calc_rows(self._conn),
        }

    def save_draft(self, tiers: list[dict]) -> dict:
        # Persisting an in-progress draft is allowed even if it is not yet
        # valid; the monotonic/non-negative gate runs at trial/apply time.
        drafts_repo.save_rows(self._conn, tiers)
        return {"items": drafts_repo.get_rows(self._conn)}

    def _load_draft_or_raise(self) -> list[dict]:
        draft = drafts_repo.get_rows(self._conn)
        if draft is None:
            raise DraftMissingError("尚未保存草稿档")
        return draft

    def trial_draft(self, kwh: float, peak: bool) -> dict:
        """Trial-calculate a probe reading against the draft only.

        Never touches the active tiers and never writes a calc run.
        """
        draft = self._load_draft_or_raise()
        validate_tiers(draft)
        pf = settings_repo.peak_factor(self._conn)
        result = calc_bill(kwh, draft, pf if peak else 1.0)
        return {"source": "draft", "run_id": None, "peak": peak, **result}

    def _before_after_summary(
        self, draft: list[dict], kwh: float, peak: bool
    ) -> dict:
        pf = settings_repo.peak_factor(self._conn)
        factor = pf if peak else 1.0
        before = calc_bill(kwh, tiers_repo.as_calc_rows(self._conn), factor)
        after = calc_bill(kwh, draft, factor)
        return {
            "applied": False,
            "source": "active",
            "kwh": before["kwh"],
            "peak": peak,
            "peak_factor": factor,
            "before": {"source": "active", **before},
            "after": {"source": "draft", **after},
        }

    def preview_apply(self, kwh: float, peak: bool) -> dict:
        """Read-only before/after comparison for the same probe reading.

        Validates the draft but replaces nothing and writes no run.
        """
        draft = self._load_draft_or_raise()
        validate_tiers(draft)
        return self._before_after_summary(draft, kwh, peak)

    def apply_draft(self, kwh: float, peak: bool) -> dict:
        """Validate the draft, then atomically replace the active ladder.

        Returns a before/after segment comparison for the same probe reading.
        On validation failure the old active ladder is left untouched.
        """
        draft = self._load_draft_or_raise()
        validate_tiers(draft)

        summary = self._before_after_summary(draft, kwh, peak)

        # Single transaction: replace active ladder and drop the consumed
        # draft together; any error rolls back and the old ladder survives.
        with self._conn:
            tiers_repo.replace_all(self._conn, draft)
            drafts_repo.clear(self._conn)

        # Read the ladder back so the summary is guaranteed to match what the
        # workbench calculates from the active tiers afterwards.
        pf = settings_repo.peak_factor(self._conn)
        factor = pf if peak else 1.0
        after = calc_bill(kwh, tiers_repo.as_calc_rows(self._conn), factor)
        summary["applied"] = True
        summary["after"] = {"source": "active", **after}
        return summary

    def list_readings(self):
        return readings_repo.list_all(self._conn)

    def readings_for_account(self, account_id: int):
        return readings_repo.for_account(self._conn, account_id)

    def settings_map(self):
        return settings_repo.get_map(self._conn)

    def run_bill(self, kwh: float, peak: bool, account_id: int | None, persist: bool):
        tiers = tiers_repo.as_calc_rows(self._conn)
        pf = settings_repo.peak_factor(self._conn)
        factor = pf if peak else 1.0
        result = calc_bill(kwh, tiers, factor)
        run_id = None
        if persist:
            run_id = runs_repo.insert(
                self._conn,
                "bill",
                {"kwh": kwh, "peak": peak, "account_id": account_id},
                result,
                account_id,
            )
        return {"run_id": run_id, **result}

    def run_compare(self, kwh: float, persist: bool):
        tiers = tiers_repo.as_calc_rows(self._conn)
        pf = settings_repo.peak_factor(self._conn)
        result = compare_plain_vs_peak(kwh, tiers, pf)
        run_id = None
        if persist:
            run_id = runs_repo.insert(self._conn, "compare", {"kwh": kwh}, result, None)
        return {"run_id": run_id, **result}

    def list_history(self, limit: int = 50):
        return runs_repo.list_recent(self._conn, limit)

    def get_run(self, run_id: int):
        return runs_repo.get(self._conn, run_id)

    def dashboard_stats(self):
        accounts = accounts_repo.list_all(self._conn)
        readings = readings_repo.list_all(self._conn)
        clean = [a for a in accounts if "种子" not in a.get("name", "")]
        dirty = [a for a in accounts if "种子" in a.get("name", "")]
        return {
            "account_count": len(accounts),
            "reading_count": len(readings),
            "clean_accounts": len(clean),
            "dirty_accounts": len(dirty),
            "recent_runs": len(runs_repo.list_recent(self._conn, 5)),
        }
