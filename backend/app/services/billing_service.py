import json

from app.db import connect
from app.engines.helpers import money
from app.engines.peak_compare import compare_plain_vs_peak
from app.engines.tier_progressive import calc_bill
from app.engines.tier_rules import validate_tier_rows
from app.repositories import accounts as accounts_repo
from app.repositories import readings as readings_repo
from app.repositories import runs as runs_repo
from app.repositories import settings as settings_repo
from app.repositories import tiers as tiers_repo


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

    def get_draft(self):
        return {
            "items": tiers_repo.list_draft(self._conn),
            "updated_at": tiers_repo.draft_updated_at(self._conn),
        }

    def save_draft(self, rows: list[dict]):
        tiers_repo.replace_draft(self._conn, rows)
        return self.get_draft()

    def _factor(self, peak: bool) -> float:
        return settings_repo.peak_factor(self._conn) if peak else 1.0

    def simulate_draft(self, kwh: float, peak: bool):
        """Trial-calc the saved draft against a probe kwh. Read-only: never
        touches the official tiers, never writes calc_runs."""
        draft = tiers_repo.list_draft(self._conn)
        if not draft:
            raise LookupError("没有已保存的草稿，请先保存草稿")
        rows = [{"up_to": d["up_to"], "price": d["price"]} for d in draft]
        factor = self._factor(peak)
        draft_res = calc_bill(kwh, rows, factor)
        official_res = calc_bill(kwh, tiers_repo.as_calc_rows(self._conn), factor)
        return {
            "source": "draft",
            "kwh": draft_res["kwh"],
            "peak": peak,
            "draft": draft_res,
            "official": official_res,
            "delta_total": money(draft_res["total"] - official_res["total"]),
        }

    def apply_draft(self, kwh: float, peak: bool):
        """Validate the draft, atomically replace the official tiers with it,
        and return a before/after segment summary for the same probe kwh.
        Any failure happens before the replace, so the old official stays."""
        draft = tiers_repo.list_draft(self._conn)
        if not draft:
            raise LookupError("没有可应用的草稿，请先保存草稿")
        rows = [{"up_to": d["up_to"], "price": d["price"]} for d in draft]
        validate_tier_rows(rows)
        factor = self._factor(peak)
        before = calc_bill(kwh, tiers_repo.as_calc_rows(self._conn), factor)
        tiers_repo.replace_official(self._conn, rows)
        # Re-read what is actually stored so the summary reflects the new official.
        after = calc_bill(kwh, tiers_repo.as_calc_rows(self._conn), factor)
        return {
            "applied": True,
            "kwh": after["kwh"],
            "peak": peak,
            "before": before,
            "after": after,
            "delta_total": money(after["total"] - before["total"]),
            "tiers": tiers_repo.list_ordered(self._conn),
        }

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
