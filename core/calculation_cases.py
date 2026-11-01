"""M63: named, immutable engineering calculation cases (``CalculationCase``).

A case stores the exact input set, the displayed results, the calculator
identity (finder path) and the method/version label of the calculator that
produced them. Cases are insert-only: reopening restores inputs into the
calculator; a re-run or a clone is saved as a NEW case with ``parent_id``, so
historical results are never overwritten. Sessions stay inside this module;
callers receive plain dicts.

W13 calculators carry no individual method versions yet; their cases are
labelled ``W13_UNVERSIONED`` so a comparison across application versions
is visibly unversioned rather than implied to be identical.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

CASE_CAPTURE_VERSION = 1
W13_UNVERSIONED = "W13 calculator (no per-method version); case capture v1"


def _clean(data: Dict[str, Any]) -> Dict[str, Any]:
    return json.loads(json.dumps(data, default=str))


def _dto(row) -> Dict[str, Any]:
    return {
        "id": row.id, "well_id": row.well_id, "wellbore_id": row.wellbore_id, "calculator": row.calculator,
        "name": row.name, "method": row.method, "method_version": row.method_version,
        "inputs": row.inputs or {}, "results": row.results or {}, "parent_id": row.parent_id,
        "note": row.note or "", "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def save_case(db, *, calculator: str, name: str, inputs: Dict[str, Any], results: Dict[str, Any],
              method: str = "", method_version: str = W13_UNVERSIONED, well_id: Optional[int] = None,
              wellbore_id: Optional[int] = None, parent_id: Optional[int] = None, note: str = "",
              user_id: Optional[int] = None, source_link: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Insert one immutable case; with ``source_link`` also its structured lineage (same transaction).

    ``source_link``: ``link_type``, ``source_table``, ``source_id``,
    ``verification_status`` and optionally ``source_method``,
    ``source_method_version``, ``recalc_method``, ``recalc_method_version``,
    ``method_changed``. The source row must exist and belong to ``well_id``.
    """
    from core.database import CalculationCase

    if not str(calculator or "").strip():
        raise ValueError("A calculator is required.")
    if not str(name or "").strip():
        raise ValueError("A case name is required.")
    if not inputs:
        raise ValueError("The case has no inputs to store.")
    with db.session_scope() as session:
        row = CalculationCase(
            well_id=well_id, wellbore_id=wellbore_id, calculator=calculator, name=str(name).strip(),
            method=method or calculator, method_version=method_version, inputs=_clean(inputs),
            results=_clean(results or {}), parent_id=parent_id, note=note, created_by=user_id,
        )
        session.add(row)
        session.flush()
        if source_link is not None:
            _add_source_link(session, row, source_link)
        return _dto(row)


LINK_TYPES = ("recalculation_of", "rerun_of", "clone_of")


def _source_row(session, table: str, record_id: int):
    from core.database import Base

    by_table = {mapper.class_.__tablename__: mapper.class_ for mapper in Base.registry.mappers}
    model = by_table.get(table)
    if model is None:
        raise ValueError(f"Unknown lineage source table {table!r}.")
    return session.get(model, record_id)


def _add_source_link(session, case_row, link: Dict[str, Any]) -> None:
    from core.database import CalculationSourceLink

    link_type = link.get("link_type", "recalculation_of")
    if link_type not in LINK_TYPES:
        raise ValueError(f"Unknown lineage type {link_type!r}.")
    table, record_id = str(link.get("source_table") or ""), link.get("source_id")
    if not table or not isinstance(record_id, int):
        raise ValueError("A lineage link needs the source table and record id.")
    if not link.get("verification_status"):
        raise ValueError("A lineage link needs a verification status.")
    source = _source_row(session, table, record_id)
    if source is None:
        raise LookupError(f"Lineage source {table}:{record_id} does not exist.")
    source_well = getattr(source, "well_id", None)
    if source_well != case_row.well_id:
        raise ValueError(f"Lineage source {table}:{record_id} belongs to well {source_well}, "
                         f"not to the case's well {case_row.well_id}.")
    session.add(CalculationSourceLink(
        case_id=case_row.id, link_type=link_type, source_table=table, source_id=record_id,
        source_well_id=source_well, source_wellbore_id=getattr(source, "wellbore_id", None),
        source_method=link.get("source_method"), source_method_version=link.get("source_method_version"),
        recalc_method=link.get("recalc_method"), recalc_method_version=link.get("recalc_method_version"),
        verification_status=str(link["verification_status"]), method_changed=bool(link.get("method_changed")),
    ))
    session.flush()


def _link_dto(row) -> Dict[str, Any]:
    return {"id": row.id, "case_id": row.case_id, "link_type": row.link_type, "source_table": row.source_table,
            "source_id": row.source_id, "source_well_id": row.source_well_id,
            "source_wellbore_id": row.source_wellbore_id, "source_method": row.source_method,
            "source_method_version": row.source_method_version, "recalc_method": row.recalc_method,
            "recalc_method_version": row.recalc_method_version,
            "verification_status": row.verification_status, "method_changed": bool(row.method_changed),
            "created_at": row.created_at.isoformat() if row.created_at else None}


def source_links(db, case_id: int) -> list:
    """Where a case came from (structured lineage)."""
    from core.database import CalculationSourceLink

    with db.session_scope() as session:
        rows = session.query(CalculationSourceLink).filter(CalculationSourceLink.case_id == case_id) \
            .order_by(CalculationSourceLink.id).all()
        return [_link_dto(r) for r in rows]


def derived_cases(db, source_table: str, source_id: int) -> list:
    """Cases derived from one history record (recalculations, re-runs, clones), oldest first."""
    from core.database import CalculationSourceLink

    with db.session_scope() as session:
        rows = session.query(CalculationSourceLink).filter(
            CalculationSourceLink.source_table == source_table, CalculationSourceLink.source_id == source_id) \
            .order_by(CalculationSourceLink.id).all()
        return [_link_dto(r) for r in rows]


def get_case(db, case_id: int) -> Dict[str, Any]:
    from core.database import CalculationCase

    with db.session_scope() as session:
        row = session.get(CalculationCase, case_id)
        if row is None:
            raise LookupError(f"Calculation case {case_id} does not exist.")
        return _dto(row)


def list_cases(db, *, calculator: Optional[str] = None, well_id: Optional[int] = None,
               text: str = "") -> List[Dict[str, Any]]:
    """Newest first; ``text`` filters on case name, calculator path and input/result keys and labels."""
    from core.database import CalculationCase

    with db.session_scope() as session:
        query = session.query(CalculationCase)
        if calculator:
            query = query.filter(CalculationCase.calculator == calculator)
        if well_id is not None:
            query = query.filter(CalculationCase.well_id == well_id)
        rows = [_dto(r) for r in query.order_by(CalculationCase.id.desc()).all()]
    needle = text.strip().lower()
    if needle:
        rows = [r for r in rows if needle in " ".join(
            [r["name"], r["calculator"]]
            + [f"{k} {_label(v)}" for part in ("inputs", "results") for k, v in r[part].items()]).lower()]
    return rows


def _label(entry: Any) -> str:
    return str(entry.get("label") or "") if isinstance(entry, dict) else ""


def _value(entry: Any) -> Any:
    return entry.get("value") if isinstance(entry, dict) and "value" in entry else entry


def compare_cases(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Inputs and results that differ between two cases (labels kept for display)."""
    def diff(left: Dict[str, Any], right: Dict[str, Any]) -> List[Dict[str, Any]]:
        out = []
        for key in sorted(set(left) | set(right)):
            va, vb = _value(left.get(key)), _value(right.get(key))
            if va != vb:
                out.append({"key": key, "label": _label(left.get(key)) or _label(right.get(key)) or key,
                            "a": va, "b": vb})
        return out

    return {
        "a": f"{a['name']} (#{a['id']})", "b": f"{b['name']} (#{b['id']})",
        "same_calculator": a["calculator"] == b["calculator"],
        "method_versions": (a["method_version"], b["method_version"]),
        "inputs": diff(a["inputs"], b["inputs"]), "results": diff(a["results"], b["results"]),
    }


def record_rerun(db, original: Dict[str, Any], results: Dict[str, Any], *, inputs: Optional[Dict[str, Any]] = None,
                 method_version: str = W13_UNVERSIONED, name: str = "") -> Dict[str, Any]:
    """Store a recalculation as a new child case; the original stays as it was.

    When the current method version differs from the original's, the new case
    says so in its note (the original version cannot be re-executed).
    """
    note = f"Recalculated from case #{original['id']}"
    if method_version != original["method_version"]:
        note += f"; method version changed from {original['method_version']!r} to {method_version!r}"
    return save_case(db, calculator=original["calculator"], name=name or f"{original['name']} (recalc)",
                     inputs=inputs if inputs is not None else original["inputs"], results=results,
                     method=original["method"], method_version=method_version, well_id=original["well_id"],
                     wellbore_id=original["wellbore_id"], parent_id=original["id"], note=note,
                     source_link={"link_type": "rerun_of", "source_table": "calculation_cases",
                                  "source_id": original["id"], "source_method": original["method"],
                                  "source_method_version": original["method_version"],
                                  "recalc_method": original["method"], "recalc_method_version": method_version,
                                  "verification_status": "RERUN",
                                  "method_changed": method_version != original["method_version"]})
