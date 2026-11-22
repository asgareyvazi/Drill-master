"""M311 (M274): component-level comparison of two frozen well-architecture revisions (read-only).

Components are matched by identity ``(kind, name)``. Several components with the same identity (e.g. two
formations both called "SYN F1") are paired identical-first, the remainder in stored order; every such remainder
row is flagged ``ambiguous`` and the ambiguity is stated (M329). For each identity the
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


def _binding_label(binding: Optional[Dict[str, Any]]) -> Optional[str]:
    """M329 (D90): the cited library item of a binding (set, version, item fingerprint); None = not bound.

    The fingerprint is in the binding's snapshot, not at its top level (the v1 diff read the top level and therefore
    showed every binding change as "unknown → unknown")."""
    if not binding:
        return None
    snap = binding.get("snapshot") or {}
    item = str(snap.get("item_fingerprint") or "")[:12] or "?"
    return f"{snap.get('set_name') or '?'} v{snap.get('set_version') or '?'} item {item}"


def _changes(old: Dict[str, Any], new: Dict[str, Any]) -> List[Dict[str, Any]]:
    changes = [{"field": f, "old": old.get(f), "new": new.get(f)} for f in FIELDS
               if (old.get(f) if old.get(f) != "" else None) != (new.get(f) if new.get(f) != "" else None)]
    if old.get(BINDING) != new.get(BINDING):
        changes.append({"field": "library binding", "old": _binding_label(old.get(BINDING)),
                        "new": _binding_label(new.get(BINDING))})
    return changes


def _pair(olds: List[Dict[str, Any]], news: List[Dict[str, Any]]) -> List[Tuple[Optional[int], Optional[int], bool]]:
    """M329: pairs of (older index, newer index, ambiguous) for one identity.

    A single occurrence on each side is matched directly. With duplicates, identical components are paired first
    (so a reordering of same-named components is UNCHANGED, not a pair of spurious changes); the remainder is
    matched in stored order and marked ambiguous, because the identity cannot tell which one the user edited."""
    if max(len(olds), len(news)) <= 1:
        return [(0 if olds else None, 0 if news else None, False)]
    pairs: List[Tuple[Optional[int], Optional[int], bool]] = []
    free_new = list(range(len(news)))
    rest_old: List[int] = []
    for i, old in enumerate(olds):
        exact = next((j for j in free_new if not _changes(old, news[j])), None)
        if exact is None:
            rest_old.append(i)
        else:
            free_new.remove(exact)
            pairs.append((i, exact, False))
    for k in range(max(len(rest_old), len(free_new))):
        pairs.append((rest_old[k] if k < len(rest_old) else None, free_new[k] if k < len(free_new) else None, True))
    return sorted(pairs, key=lambda p: (p[1] if p[1] is not None else len(news), p[0] if p[0] is not None else -1))


def compare_components(older: List[Dict[str, Any]], newer: List[Dict[str, Any]]) -> Dict[str, Any]:
    from core import well_architecture as wa

    old_items, new_items = wa.normalize(older)[0], wa.normalize(newer)[0]
    old_groups, new_groups = _groups(old_items), _groups(new_items)
    rows: List[Dict[str, Any]] = []
    notes: List[str] = []
    order = list(dict.fromkeys(list(old_groups) + list(new_groups)))
    for key in order:
        olds, news = old_groups.get(key, []), new_groups.get(key, [])
        pairs = _pair(olds, news)
        if max(len(olds), len(news)) > 1:
            unresolved = sum(1 for p in pairs if p[2])
            notes.append(f"{key[0]} '{key[1]}' occurs {len(olds)}× in the older and {len(news)}× in the newer "
                         f"revision; identical ones matched first, "
                         + (f"{unresolved} matched in stored order (ambiguous)" if unresolved else
                            "no ambiguity left"))
        for oi, ni, ambiguous in pairs:
            old = olds[oi] if oi is not None else None
            new = news[ni] if ni is not None else None
            dup = max(len(olds), len(news)) > 1          # occurrence numbers only where the identity repeats
            base = {"kind": key[0], "name": key[1], "ambiguous": ambiguous,
                    "occurrence_old": oi + 1 if dup and oi is not None else None,
                    "occurrence_new": ni + 1 if dup and ni is not None else None}
            if old is None:
                rows.append({**base, "status": ADDED, "changes": [], "new": new})
                continue
            if new is None:
                rows.append({**base, "status": REMOVED, "changes": [], "old": old})
                continue
            changes = _changes(old, new)
            rows.append({**base, "status": CHANGED if changes else UNCHANGED, "changes": changes,
                         "old": old, "new": new})
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
                   "well_id": older["well_id"], "pinned_cases": _pinned_cases(db, older["id"], older["well_id"])})
    return result


def _pinned_cases(db, revision_id: int, well_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Saved work whose inputs pin the older revision (shown, never recalculated).

    M323 (A-1): uses the canonical lookup of Calculation History (``_architecture_users``), so casing-design runs
    (``casing_calculations``) are listed next to calculation cases (cement worksheets, M317 reconciliations)."""
    from core import calculation_history as ch
    from core import database as d

    out: List[Dict[str, Any]] = []
    models = {d.CasingCalculationRecord.__tablename__: d.CasingCalculationRecord,
              d.CalculationCase.__tablename__: d.CalculationCase}
    with db.session_scope() as session:
        for key in ch._architecture_users(session, d, revision_id, well_id):
            table, _sep, rid = key.partition(":")
            row = session.get(models[table], int(rid))
            name = (getattr(row, "name", None) or getattr(row, "label", None) or "") if row else ""
            calculator = getattr(row, "calculator", None) or ("Casing design" if table != "calculation_cases" else "")
            out.append({"key": key, "table": table, "id": int(rid), "name": name, "calculator": calculator})
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
            f"{p['key']} {p['name']}".rstrip() for p in result["pinned_cases"]) + " (not recalculated).")
    lines += [f"Note: {n}." for n in result["notes"]]
    return lines


# ---------------------------------------------------------------------------
# M329: table rows and CSV / Excel export
# ---------------------------------------------------------------------------

TABLE_COLUMNS = ("Status", "Kind", "Name", "Occurrence (older → newer)", "Field", "Older", "Newer", "Ambiguous")
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _cell(value: Any) -> Any:
    """Export cell: unknown stays an empty cell (never 0); free text cannot start a spreadsheet formula."""
    if value in (None, ""):
        return ""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def table_rows(result: Dict[str, Any], *, include_unchanged: bool = False) -> List[Tuple[Any, ...]]:
    """One row per changed field; ADDED / REMOVED (and UNCHANGED on request) are a single row without a field."""
    out: List[Tuple[Any, ...]] = []
    for r in result["rows"]:
        if r["status"] == UNCHANGED and not include_unchanged:
            continue
        occurrence = (f"{r.get('occurrence_old') or '—'} → {r.get('occurrence_new') or '—'}"
                      if r.get("occurrence_old") is not None or r.get("occurrence_new") is not None else "")
        flag = "yes" if r.get("ambiguous") else ""
        if r["status"] == CHANGED:
            for ch in r["changes"]:
                out.append((r["status"], r["kind"], r["name"], occurrence, ch["field"], ch["old"], ch["new"], flag))
        else:
            out.append((r["status"], r["kind"], r["name"], occurrence, "", None, None, flag))
    return out


def export_metadata(result: Dict[str, Any]) -> List[Tuple[str, Any]]:
    meta: List[Tuple[str, Any]] = [("method", result["version"])]
    for side in ("older", "newer"):
        if side in result:
            info = result[side]
            meta += [(f"{side} revision", info["revision"]), (f"{side} revision id", info["id"]),
                     (f"{side} components SHA-256", info["components_sha256"]),
                     (f"{side} created", str(info.get("created_at") or ""))]
    if "well_id" in result:
        meta.append(("well id", result["well_id"]))
    c = result["counts"]
    meta.append(("counts", f"{c[ADDED]} added, {c[REMOVED]} removed, {c[CHANGED]} changed, "
                           f"{c[UNCHANGED]} unchanged"))
    meta.append(("geometry changed for", ", ".join(result["affected_strings"])))
    meta.append(("cases pinned to the older revision (not recalculated)",
                 ", ".join(f"{p['key']} {p['name']}".rstrip() for p in result.get("pinned_cases") or [])))
    meta += [("note", n) for n in result["notes"]]
    meta.append(("null policy", "An empty Older/Newer cell means unknown (never zero)."))
    return meta


def export(result: Dict[str, Any], path, *, include_unchanged: bool = False) -> str:
    """Write the comparison as CSV or XLSX (by file suffix): metadata block, blank row, then the table."""
    from pathlib import Path

    target = Path(path)
    suffix = target.suffix.lower()
    if suffix not in (".csv", ".xlsx"):
        raise ArchitectureDiffError("Export as .csv or .xlsx.")
    meta = [(k, _cell(v)) for k, v in export_metadata(result)]
    body = [tuple(_cell(v) for v in row) for row in table_rows(result, include_unchanged=include_unchanged)]
    if suffix == ".csv":
        import csv

        with target.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerows(meta)
            writer.writerow([])
            writer.writerow(TABLE_COLUMNS)
            writer.writerows(body)
    else:
        from openpyxl import Workbook

        book = Workbook()
        sheet = book.active
        sheet.title = "Architecture diff"
        for row in meta:
            sheet.append(list(row))
        sheet.append([])
        sheet.append(list(TABLE_COLUMNS))
        for row in body:
            sheet.append(list(row))
        book.save(target)
    return str(target)
