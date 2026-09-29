"""Totals for the W7 bulk-material table, preserving nullable stock values."""
from __future__ import annotations


_FIELDS = ("initial", "received", "used", "current")


def summarize_bulk_display_rows(rows):
    """Summarize displayed bulk rows; no rows retain the established empty-set 0.0.

    Each row maps ``initial``, ``received``, ``used`` and ``current`` to the cell
    text shown in W7. Blank stock and em-dash cells represent unknown; blank
    movement cells follow the established no-movement=0.0 convention. Malformed
    and non-finite values are unknown. A column total is known only when every
    row in that column is known, matching the database ``complete_total``
    contract. A missing value in one column must not discard known values from
    the other columns.
    """
    rows = list(rows)
    if not rows:
        return {**{field: 0.0 for field in _FIELDS}, "count": 0}

    totals = {field: 0.0 for field in _FIELDS}
    complete = {field: True for field in _FIELDS}
    for row in rows:
        for field in _FIELDS:
            raw = row.get(field)
            if raw is None or str(raw).strip() == "—":
                complete[field] = False
                continue
            if not str(raw).strip():
                if field in ("received", "used"):
                    continue  # documented blank movement means no movement (0.0)
                complete[field] = False
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                complete[field] = False
                continue
            if value != value or value in (float("inf"), float("-inf")):
                complete[field] = False
                continue
            totals[field] += value

    return {
        **{field: totals[field] if complete[field] else None for field in _FIELDS},
        "count": len(rows),
    }
