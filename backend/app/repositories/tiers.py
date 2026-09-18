import sqlite3
from datetime import datetime, timezone


def list_ordered(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT id, up_to, price, sort_order FROM tiers ORDER BY sort_order").fetchall()
    return [dict(r) for r in rows]


def as_calc_rows(conn: sqlite3.Connection) -> list[dict]:
    return [{"up_to": r["up_to"], "price": r["price"]} for r in list_ordered(conn)]


def list_draft(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, up_to, price, sort_order FROM tier_drafts ORDER BY sort_order"
    ).fetchall()
    return [dict(r) for r in rows]


def draft_updated_at(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT MAX(updated_at) AS ts FROM tier_drafts").fetchone()
    return row["ts"] if row else None


def replace_draft(conn: sqlite3.Connection, rows: list[dict]) -> None:
    """Atomically replace the whole (single-slot) draft sequence."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        conn.execute("DELETE FROM tier_drafts")
        conn.executemany(
            "INSERT INTO tier_drafts(up_to, price, sort_order, updated_at) VALUES (?,?,?,?)",
            [(r["up_to"], r["price"], i, now) for i, r in enumerate(rows, start=1)],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def replace_official(conn: sqlite3.Connection, rows: list[dict]) -> None:
    """Atomically replace the official tier sequence (delete + insert in one transaction)."""
    try:
        conn.execute("DELETE FROM tiers")
        conn.executemany(
            "INSERT INTO tiers(up_to, price, sort_order) VALUES (?,?,?)",
            [(r["up_to"], r["price"], i) for i, r in enumerate(rows, start=1)],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
