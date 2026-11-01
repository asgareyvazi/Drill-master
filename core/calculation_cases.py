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
              user_id: Optional[int] = None) -> Dict[str, Any]:
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
        return _dto(row)


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
                     wellbore_id=original["wellbore_id"], parent_id=original["id"], note=note)
