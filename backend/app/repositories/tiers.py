import sqlite3


def list_ordered(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT id, up_to, price, sort_order FROM tiers ORDER BY sort_order").fetchall()
    return [dict(r) for r in rows]


def as_calc_rows(conn: sqlite3.Connection) -> list[dict]:
    return [{"up_to": r["up_to"], "price": r["price"]} for r in list_ordered(conn)]


def replace_all(conn: sqlite3.Connection, tiers: list[dict]) -> None:
    """Atomically replace the whole ladder.

    Caller owns the transaction: nothing is committed here so a failure rolls
    back and the previously active ladder stays intact.
    """
    conn.execute("DELETE FROM tiers")
    conn.executemany(
        "INSERT INTO tiers(up_to, price, sort_order) VALUES (?,?,?)",
        [(t.get("up_to"), float(t["price"]), i + 1) for i, t in enumerate(tiers)],
    )
