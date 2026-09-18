import json
import sqlite3

# One draft tier sequence per scope; the product currently has a single global ladder.
DEFAULT_SCOPE = "default"


def get_rows(conn: sqlite3.Connection, scope: str = DEFAULT_SCOPE) -> list[dict] | None:
    row = conn.execute(
        "SELECT tiers_json FROM tier_drafts WHERE scope=?", (scope,)
    ).fetchone()
    if not row:
        return None
    return json.loads(row["tiers_json"])


def save_rows(
    conn: sqlite3.Connection, tiers: list[dict], scope: str = DEFAULT_SCOPE
) -> None:
    conn.execute(
        """
        INSERT INTO tier_drafts(scope, tiers_json, updated_at)
        VALUES (?,?,datetime('now'))
        ON CONFLICT(scope) DO UPDATE SET
            tiers_json=excluded.tiers_json,
            updated_at=datetime('now')
        """,
        (scope, json.dumps(tiers, ensure_ascii=False)),
    )
    conn.commit()


def clear(conn: sqlite3.Connection, scope: str = DEFAULT_SCOPE) -> None:
    """Delete the draft. Does not commit: callers may run it inside a transaction."""
    conn.execute("DELETE FROM tier_drafts WHERE scope=?", (scope,))
