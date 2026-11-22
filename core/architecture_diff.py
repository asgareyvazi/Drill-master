"""M311 (M274): component-level comparison of two frozen well-architecture revisions (read-only).

Components are matched by identity ``(kind, name)``. Several components with the same identity (e.g. two
formations both called "SYN F1") are matched in stored order, and the ambiguity is stated. For each identity the
result is ADDED, REMOVED, CHANGED (with every changed field, old → new) or UNCHANGED.

Rules:
* Values are compared as stored. Blank stays None and is shown as "unknown"; it never becomes 0. A field that went
  from a value to unknown is a change.
* Both revisions are loaded through ``well_architecture.get_revision``, which refuses a revision whose SHA-256
  check fails. A tampered revision is therefore never compared.
* Both revisions must belong to the same well.
* The comparison also states the derived consequences that matter to the user: a string whose depth, OD or ID
  changed invalidates worksheets (cement annulus, casing inputs) pinned to the older revision. Those cases are
  listed, never recalculated.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

DIFF_VERSION = "M311 architecture revision diff v1"
ADDED, REMOVED, CHANGED, UNCHANGED = "ADDED", "REMOVED", "CHANGED", "UNCHANGED"
FIELDS = ("top_md", "bottom_md", "od_in", "id_in", "hole_in", "weight_ppf", "grade", "note")
GEOMETRY = ("top_md", "bottom_md", "od_in", "id_in", "hole_in")
BINDING = "tubular_reference"


class ArchitectureDiffError(ValueError):
    pass


def _key(item: Dict[str, Any]) -> Tuple[str, str]:
    return item.get("kind") or "", item.get("name") or ""


def _show(value: Any) -> str:
    return "unknown" if value in (None, "") else (f"{value:g}" if isinstance(value, float) else str(value))


def _groups(items: List[Dict[str, Any]]) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    out: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for item in items:
        out.setdefault(_key(item), []).append(item)
    return out


def compare_components(older: List[Dict[str, Any]], newer: List[Dict[str, Any]]) -> Dict[str, Any]:
    from core import well_architecture as wa

    old_items, new_items = wa.normalize(older)[0], wa.normalize(newer)[0]
    old_groups, new_groups = _groups(old_items), _groups(new_items)
    rows: List[Dict[str, Any]] = []
    notes: List[str] = []
    order = list(dict.fromkeys(list(old_groups) + list(new_groups)))
    for key in order:
        olds, news = old_groups.get(key, []), new_groups.get(key, [])
        if max(len(olds), len(news)) > 1:
            notes.append(f"{key[0]} '{key[1]}' occurs {len(olds)}× in the older and {len(news)}× in the newer "
                         f"revision; matched in stored order")
        for index in range(max(len(olds), len(news))):
            old = olds[index] if index < len(olds) else None
            new = news[index] if index < len(news) else None
            if old is None:
                rows.append({"kind": key[0], "name": key[1], "status": ADDED, "changes": [], "new": new})
                continue
            if new is None:
                rows.append({"kind": key[0], "name": key[1], "status": REMOVED, "changes": [], "old": old})
                continue
            changes = [{"field": f, "old": old.get(f), "new": new.get(f)} for f in FIELDS
                       if (old.get(f) if old.get(f) != "" else None) != (new.get(f) if new.get(f) != "" else None)]
            if old.get(BINDING) != new.get(BINDING):
                changes.append({"field": "library binding", "old": (old.get(BINDING) or {}).get("fingerprint"),
                                "new": (new.get(BINDING) or {}).get("fingerprint")})
            rows.append({"kind": key[0], "name": key[1], "status": CHANGED if changes else UNCHANGED,
                         "changes": changes, "old": old, "new": new})
    affected = sorted({r["name"] for r in rows if r["kind"] in wa.STRINGS + ("cement",) and (
        r["status"] in (ADDED, REMOVED) or any(c["field"] in GEOMETRY for c in r["changes"]))})
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in (ADDED, REMOVED, CHANGED, UNCHANGED)}
    return {"version": DIFF_VERSION, "rows": rows, "counts": counts, "notes": notes,
            "affected_strings": affected, "identical": counts[ADDED] == counts[REMOVED] == counts[CHANGED] == 0}


def compare_revisions(db, older_id: int, newer_id: int) -> Dict[str, Any]:
    from core import well_architecture as wa

    older, newer = wa.get_revision(db, older_id), wa.get_revision(db, newer_id)
    if older["well_id"] != newer["well_id"]:
        raise ArchitectureDiffError("The two architecture revisions belong to different wells.")
    if older["id"] == newer["id"]:
        raise ArchitectureDiffError("Select two different revisions.")
    if older["revision"] > newer["revision"]:
        older, newer = newer, older
    result = compare_components(older["components"], newer["components"])
    result.update({"older": {k: older[k] for k in ("id", "revision", "components_sha256", "created_at")},
                   "newer": {k: newer[k] for k in ("id", "revision", "components_sha256", "created_at")},
                   "well_id": older["well_id"], "pinned_cases": _pinned_cases(db, older["id"])})
    return result


def _pinned_cases(db, revision_id: int) -> List[Dict[str, Any]]:
    """Calculation cases whose inputs pin the older revision (shown, never recalculated)."""
    from core.database import CalculationCase

    out: List[Dict[str, Any]] = []
    with db.session_scope() as session:
        for case in session.query(CalculationCase).order_by(CalculationCase.id):
            inputs = case.inputs or {}
            entry = inputs.get("architecture_revision_id") if isinstance(inputs, dict) else None
            value = entry.get("value") if isinstance(entry, dict) else entry
            if value == revision_id:
                out.append({"id": case.id, "calculator": case.calculator, "name": case.name})
    return out


def summary_lines(result: Dict[str, Any], *, limit: Optional[int] = None) -> List[str]:
    c = result["counts"]
    head = (f"Architecture rev {result['older']['revision']} → rev {result['newer']['revision']}: "
            if "older" in result else "")
    lines = [head + ("identical components." if result["identical"] else
                     f"{c[ADDED]} added, {c[REMOVED]} removed, {c[CHANGED]} changed, {c[UNCHANGED]} unchanged.")]
    shown = [r for r in result["rows"] if r["status"] != UNCHANGED]
    for r in shown[:limit] if limit else shown:
        if r["status"] == CHANGED:
            lines.append(f"CHANGED {r['kind']} '{r['name']}': " + "; ".join(
                f"{ch['field']} {_show(ch['old'])} → {_show(ch['new'])}" for ch in r["changes"]))
        else:
            lines.append(f"{r['status']} {r['kind']} '{r['name']}'")
    if result["affected_strings"]:
        lines.append("Geometry changed for: " + ", ".join(result["affected_strings"])
                     + " — worksheets pinned to the older revision are not updated.")
    if result.get("pinned_cases"):
        lines.append("Cases pinned to the older revision: " + ", ".join(
            f"#{p['id']} {p['name']}" for p in result["pinned_cases"]) + " (not recalculated).")
    lines += [f"Note: {n}." for n in result["notes"]]
    return lines
