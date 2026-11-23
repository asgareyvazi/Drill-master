"""M303/M304: clone contract for every calculation-history adapter, and clone provenance.

M303 — adapter matrix. ``calculation_history._adapters()`` maps eleven tables to history entries. Each table has
one row in ``ADAPTER_MATRIX`` that says what a clone needs. ``clone_check`` applies it and refuses an invalid
clone with a reason **before** anything is written:

* the table has no matrix row (a new adapter must be classified, never cloned by default);
* the inputs or the stored results are missing or unreadable (legacy JSON that could not be parsed);
* an integrity hash no longer matches (survey stations, architecture components);
* a required input is missing (survey stations, architecture components);
* the source row no longer exists.

M304 — provenance. ``clone_provenance`` reads a clone's ``clone_of`` link and reports the source identity, the
method and version that were copied, and states that the clone was **not recalculated and never approved**. The
link has no ``source_created_at``, so identity is checked by time: a source row created after the link was written
is a different record that reused the id (``SOURCE_REPLACED``); a source without a creation time can only be
``IDENTITY_WEAK``. M365 (D87): a link written from M365 on carries the source's content fingerprint
(``core.record_identity``); it decides VERIFIED / SOURCE_REPLACED even for equal or NULL timestamps. Older links
keep the time rule (``identity_basis`` TIMESTAMP_ONLY). Nothing here writes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

CONTRACT = "calculation-clone-contract-v1"
CLONE_LABEL = "CLONE — inputs and stored results copied; NOT recalculated; NOT approved"

# identity outcomes of a clone's source link (M304)
VERIFIED, SOURCE_REPLACED, IDENTITY_WEAK, SOURCE_MISSING = "VERIFIED", "SOURCE_REPLACED", "IDENTITY_WEAK", \
    "SOURCE_MISSING"


@dataclass(frozen=True)
class AdapterContract:
    table: str
    source: str
    clone: str                       # ALLOWED or REFUSED
    route: str                       # how the clone is stored
    required_inputs: Tuple[str, ...] = ()
    integrity: str = ""              # headline key that must read VERIFIED
    results_from: str = "full_results, else results"
    note: str = ""


_SNAPSHOT_NOTE = "frozen input snapshot and stored result copied; the scope label of the source is kept in the note"
ADAPTER_MATRIX: Dict[str, AdapterContract] = {
    **{table: AdapterContract(table, source, "ALLOWED", "calculation_cases.save_case + clone_of link",
                              note=_SNAPSHOT_NOTE)
       for table, source in (("torque_drag_calculations", "Torque & drag"),
                             ("casing_calculations", "Casing design"),
                             ("cement_calculations", "Cement volumes"),
                             ("mse_calculations", "MSE"),
                             ("mud_volume_calculations", "Mud volume"),
                             ("well_control_kill_sheet_calculations", "Kill sheet"))},
    "trajectory_calculations": AdapterContract(
        "trajectory_calculations", "Trajectory", "ALLOWED", "calculation_cases.save_case + clone_of link",
        note="a legacy row keeps the version text 'unversioned (legacy)'; it is never given a version"),
    "calculation_cases": AdapterContract(
        "calculation_cases", "Calculation case", "ALLOWED", "calculation_cases.clone_case (parent_id + clone_of)",
        results_from="results"),
    "directional_plan_revisions": AdapterContract(
        "directional_plan_revisions", "Directional plan", "ALLOWED", "calculation_cases.save_case + clone_of link",
        note="the clone is a calculation case, not a new plan revision (plan revisions come from the planner)"),
    "survey_revisions": AdapterContract(
        "survey_revisions", "Survey revision", "ALLOWED", "calculation_cases.save_case + clone_of link",
        required_inputs=("stations",), integrity="integrity",
        note="refused when the stored stations no longer match their SHA-256"),
    "well_architecture_revisions": AdapterContract(
        "well_architecture_revisions", "Well architecture", "ALLOWED", "calculation_cases.save_case + clone_of link",
        required_inputs=("components",), integrity="integrity",
        note="refused when the stored components no longer match their SHA-256"),
}


def adapter_matrix() -> List[Dict[str, Any]]:
    """The matrix as rows (for documentation and the workbench), in adapter order."""
    from core import calculation_history as ch

    return [asdict(ADAPTER_MATRIX[model.__tablename__]) if model.__tablename__ in ADAPTER_MATRIX else
            {"table": model.__tablename__, "source": "", "clone": "REFUSED", "route": "",
             "note": "no clone contract for this adapter"}
            for model, _adapt in ch._adapters()]


def _unreadable(value: Any) -> bool:
    return isinstance(value, dict) and set(value) == {"raw"}       # calculation_history._json's legacy fallback


def clone_check(entry, db=None) -> Tuple[bool, str]:
    """``(True, "")`` when ``entry`` may be cloned, otherwise ``(False, reason)``. Never writes."""
    contract = ADAPTER_MATRIX.get(entry.table)
    if contract is None or contract.clone != "ALLOWED":
        return False, f"{entry.table} has no clone contract; it cannot be cloned."
    if not isinstance(entry.inputs, dict) or not entry.inputs:
        return False, f"{entry.key} has no readable inputs; it cannot be cloned."
    if _unreadable(entry.inputs):
        return False, f"{entry.key} has unreadable stored inputs (legacy JSON); it cannot be cloned."
    results = entry.full_results if contract.results_from.startswith("full") and entry.full_results \
        else entry.results
    if not isinstance(results, dict) or not results:
        return False, f"{entry.key} has no stored results to copy; re-run it instead of cloning."
    if _unreadable(results):
        return False, f"{entry.key} has unreadable stored results (legacy JSON); it cannot be cloned."
    missing = [key for key in contract.required_inputs if not entry.inputs.get(key)]
    if missing:
        return False, f"{entry.key} is missing {', '.join(missing)}; it cannot be cloned."
    if contract.integrity:
        status = (entry.results or {}).get(contract.integrity)
        if status != "VERIFIED":
            return False, (f"{entry.key} failed its integrity check ({status or 'not checked'}); "
                           f"a copy would carry data that no longer matches its hash.")
    if db is not None:
        from core.calculation_cases import _source_row

        with db.session_scope() as session:
            if _source_row(session, entry.table, entry.record_id) is None:
                return False, f"{entry.key} no longer exists."
    return True, ""


def _as_time(value):
    from datetime import datetime

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:  # silent-ok: an unparseable timestamp is an unknown time -> IDENTITY_WEAK, never VERIFIED
            return None
    return value


def _naive(value):
    return value.replace(tzinfo=None) if value is not None and getattr(value, "tzinfo", None) else value


def clone_provenance(db, case_id: int) -> Dict[str, Any]:
    """Where a clone came from, whether that source is still the same record, and what the clone is not."""
    from core import calculation_cases as cc
    from core.calculation_cases import _source_row

    case = cc.get_case(db, case_id)
    links = [link for link in cc.source_links(db, case_id) if link["link_type"] == "clone_of"]
    out: Dict[str, Any] = {
        "contract": CONTRACT, "case_id": case_id, "is_clone": bool(links), "label": CLONE_LABEL if links else "",
        "method": case["method"], "method_version": case["method_version"],
        "recalculated": False if links else None, "approved": False,
    }
    if not links:
        out["reason"] = "this case has no clone_of link; it is not a clone"
        return out
    link = links[-1]
    out.update(source_key=f"{link['source_table']}:{link['source_id']}", source_table=link["source_table"],
               source_id=link["source_id"], source_method=link["source_method"],
               source_method_version=link["source_method_version"],
               method_kept=(case["method_version"] == link["source_method_version"]),
               verification_status=link["verification_status"], linked_at=link["created_at"])
    from core import record_identity

    with db.session_scope() as session:
        source = _source_row(session, link["source_table"], link["source_id"])
        if source is None:
            out.update(identity=SOURCE_MISSING, reason="the source record no longer exists; the clone keeps its copy")
            return out
        born = _naive(_as_time(getattr(source, "created_at", None)))
        pinned = record_identity.compare(link["source_table"], link.get("source_fingerprint"), source)
    out["identity_basis"] = (record_identity.CONTENT_PINNED if pinned in (record_identity.MATCH,
                                                                           record_identity.DIFFERENT)
                             else record_identity.TIMESTAMP_ONLY)
    linked = _naive(_as_time(link["created_at"]))
    if pinned == record_identity.DIFFERENT:            # M365 (D87): the content fingerprint is decisive when it differs
        out.update(identity=SOURCE_REPLACED,
                   reason=f"{out['source_key']} no longer has the content fingerprint recorded with the link: the id "
                          f"now belongs to a different record (or its frozen content changed), which is not the "
                          f"clone's source")
        return out
    if pinned == record_identity.MATCH:                # equal content: the time rule still catches a newer row
        if born is not None and linked is not None and born > linked:
            out.update(identity=SOURCE_REPLACED,
                       reason=f"{out['source_key']} has identical content but was created after the clone was "
                              f"linked: it is a different record that reused the id")
        else:
            out.update(identity=VERIFIED, reason="the source record has the content fingerprint recorded with the "
                                                 "link (same record)")
        return out
    if born is None or linked is None:
        out.update(identity=IDENTITY_WEAK,
                   reason="the source or the link has no creation time, so a reused id cannot be ruled out")
    elif born > linked:
        out.update(identity=SOURCE_REPLACED,
                   reason=f"{out['source_key']} was created after the clone was linked: the id now belongs to a "
                          f"different record, which is not the clone's source")
    else:
        out.update(identity=VERIFIED, reason="the source record predates the link (same record)")
    return out


def source_entry(db, provenance: Dict[str, Any]):
    """The history entry of a clone's source when its identity is VERIFIED or IDENTITY_WEAK, else None."""
    from core import calculation_history as ch

    if provenance.get("identity") not in (VERIFIED, IDENTITY_WEAK):
        return None
    for model, adapt in ch._adapters():
        if model.__tablename__ == provenance["source_table"]:
            with db.session_scope() as session:
                row = session.get(model, provenance["source_id"])
                return adapt(row) if row is not None else None
    return None


def side_by_side(db, case_id: int) -> Dict[str, Any]:
    """M306: the clone and its source next to each other. A clone is a copy, not a rerun: the comparison shows
    whether the copy still equals its source; it never recalculates either side."""
    from core import calculation_history as ch

    provenance = clone_provenance(db, case_id)
    out: Dict[str, Any] = {"provenance": provenance, "rows": [], "rerun": False,
                           "statement": "A clone is a copy of stored inputs and results, not a rerun; nothing was "
                                        "recalculated for this view."}
    if not provenance["is_clone"]:
        out["status"] = "NOT_A_CLONE"
        return out
    source = source_entry(db, provenance)
    if source is None:
        out["status"] = f"SOURCE_NOT_COMPARABLE ({provenance['identity']})"
        return out
    clone = next((e for model, adapt in ch._adapters() if model.__tablename__ == "calculation_cases"
                  for e in [_one(db, model, adapt, case_id)] if e is not None), None)
    source_results = source.full_results or source.results or {}
    rows = []
    for section, left, right in (("input", clone.inputs, source.inputs), ("result", clone.results, source_results)):
        flat_left, flat_right = ch.flatten(left), ch.flatten(right)
        for key in sorted(set(flat_left) | set(flat_right)):
            a, b = flat_left.get(key), flat_right.get(key)
            rows.append({"section": section, "key": key, "clone": a, "source": b,
                         "status": "SAME" if a == b else ("ONLY IN CLONE" if key not in flat_right else
                                                          "ONLY IN SOURCE" if key not in flat_left else "DIFFERENT")})
    out["rows"] = rows
    out["status"] = "IDENTICAL COPY" if all(r["status"] == "SAME" for r in rows) else "DIFFERS FROM SOURCE"
    out["meta"] = [("Method", clone.method, source.method), ("Version", clone.version, source.version),
                   ("Created", clone.created_at, source.created_at), ("Scope", clone.scope, source.scope)]
    return out


def _one(db, model, adapt, record_id: int):
    with db.session_scope() as session:
        row = session.get(model, record_id)
        return adapt(row) if row is not None else None


def provenance_line(provenance: Dict[str, Any]) -> str:
    if not provenance.get("is_clone"):
        return "Not a clone."
    return (f"{CLONE_LABEL}. Clone of {provenance['source_key']} ({provenance.get('source_method') or '?'} "
            f"{provenance.get('source_method_version') or '?'}). Source identity: {provenance['identity']} – "
            f"{provenance['reason']}.")


def explain(entry, db=None) -> Optional[str]:
    """The refusal reason for ``entry`` or None when it can be cloned (used by the workbench tooltip)."""
    ok, reason = clone_check(entry, db)
    return None if ok else reason
