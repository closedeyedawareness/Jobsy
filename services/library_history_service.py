"""
library_history_service.py — reading the audit trail the library already keeps.

Every write to a reference table fires a trigger that appends a row to
`library_audit` (org, table, row, action, the whole old and new row, when, and
by whom). Migration 0003 made that genuinely append-only: even the service key
the importer uses cannot rewrite or erase it.

Until now nothing read it. A change history that is written and never shown is
indistinguishable, from the user's side, from no history at all — and it is the
only place that can answer "who changed this band, and when" once the workbook
has stopped being the record.

This is deliberately read-only and deliberately small: it lists what changed and
names the fields that differ. It is not a diff viewer, and it does not attempt to
reconstruct a row at a point in time — `old_row` is right there for that, and
inventing a restore path is a bigger decision than a panel.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

__all__ = ["recent_changes", "changed_fields", "summarise"]

#: Columns whose movement says nothing a reader wants to see in a change list.
_NOISE_FIELDS = frozenset({"id", "org_id", "revision_id", "created_at"})


def changed_fields(old_row: Optional[dict], new_row: Optional[dict]) -> list[str]:
    """The field names whose value actually moved.

    An INSERT has no old row and a DELETE has no new one; in both cases the
    interesting answer is "all of it", so the list stays empty and the action
    column carries the meaning instead of a wall of field names.
    """
    if not isinstance(old_row, dict) or not isinstance(new_row, dict):
        return []
    return sorted(
        key for key in set(old_row) | set(new_row)
        if key not in _NOISE_FIELDS and old_row.get(key) != new_row.get(key)
    )


def recent_changes(client, org_id: Optional[str] = None, limit: int = 200) -> pd.DataFrame:
    """The most recent audit rows, newest first, as a readable frame.

    Returns an empty frame rather than raising when the trail is empty or the
    query fails: a history panel that takes the page down with it is worse than
    a history panel that says there is nothing to show.
    """
    try:
        query = (client.table("library_audit")
                 .select("changed_at,table_name,action,changed_by,old_row,new_row"))
        if org_id:
            query = query.eq("org_id", org_id)
        resp = query.order("changed_at", desc=True).limit(limit).execute()
        rows = resp.data or []
    except Exception:
        return pd.DataFrame()

    if not rows:
        return pd.DataFrame()

    out = []
    for r in rows:
        fields = changed_fields(r.get("old_row"), r.get("new_row"))
        out.append({
            "When": str(r.get("changed_at") or "")[:19].replace("T", " "),
            "Table": r.get("table_name"),
            "Action": r.get("action"),
            "By": _short_actor(r.get("changed_by")),
            "Fields changed": ", ".join(fields) if fields else "—",
            "Field count": len(fields),
        })
    return pd.DataFrame(out)


def summarise(changes: pd.DataFrame) -> dict:
    """Counts a panel can put in tiles without recomputing them in the page."""
    if changes is None or changes.empty:
        return {"rows": 0, "tables": 0, "inserts": 0, "updates": 0, "deletes": 0, "latest": None}
    action = changes["Action"].astype(str)
    return {
        "rows": len(changes),
        "tables": changes["Table"].nunique(),
        "inserts": int((action == "INSERT").sum()),
        "updates": int((action == "UPDATE").sum()),
        "deletes": int((action == "DELETE").sum()),
        "latest": changes["When"].iloc[0] if len(changes) else None,
    }


def _short_actor(actor) -> str:
    """`changed_by` defaults to the raw JWT claims blob; show something readable.

    The claims JSON is long, and the part a reader wants is the role. Falls back
    to the value as given, because a database user name is already readable and
    guessing at its shape would lose it.
    """
    text = str(actor or "").strip()
    if not text:
        return "—"
    if text.startswith("{"):
        import json
        try:
            claims = json.loads(text)
        except Exception:
            return text[:60]
        for key in ("email", "sub", "role"):
            if claims.get(key):
                return str(claims[key])
        return "authenticated"
    return text
