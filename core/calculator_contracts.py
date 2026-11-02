"""Structured calculator contracts (M73).

A contract gives one calculator a stable identity and a data contract:

* ``stable_id`` and ``schema_version`` - what a stored case was captured with;
* ``method_id`` / ``method_version`` - the method that produced the results;
* field IDs with canonical units for inputs and results, bound to the
  calculator's form labels (the generic W13 capture keeps working);
* ``recalculate`` - the CURRENT method, reusing the existing engine.

A stored case is reproducible only when its method version is still available
here. Cases captured before M73 carry ``calculation_cases.W13_UNVERSIONED`` and stay NOT
REPRODUCIBLE: nothing records which method produced them. Stored results are
display text, so comparisons use the documented display rounding of each
field (half a unit in the last displayed decimal) as the tolerance.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

CONTRACT_REGISTRY_VERSION = "M73 calculator contracts v1"


@dataclass(frozen=True)
class FieldSpec:
    field_id: str
    label: str            # the form label the generic capture records
    unit: str             # canonical unit of the stored value
    decimals: Optional[int] = None   # displayed decimals (results): tolerance = 0.5 * 10**-decimals


@dataclass(frozen=True)
class Contract:
    stable_id: str
    calculator: str       # the W13 finder path
    schema_version: int
    method_id: str
    method_version: str
    inputs: Tuple[FieldSpec, ...]
    results: Tuple[FieldSpec, ...]
    recalculate: Callable[[Dict[str, float]], Dict[str, Optional[float]]] = field(compare=False)
    reference: str = ""


def _quick_calc(values: Dict[str, float]) -> Dict[str, Optional[float]]:
    """Pipe capacity/displacement; the same engine calls as W13 ``_vol_update_quick``."""
    from core.hydraulics_engine import AdvancedHydraulicsEngine as engine

    od, inner, length = values["od"], values["id"], values["length"]
    if not od > inner > 0:
        raise ValueError("OD must be greater than ID and ID greater than zero")
    capacity = engine.calc_pipe_capacity_bbl_ft(inner) * 3.28084
    displacement = engine.calc_pipe_displacement_bbl_ft(od, inner) * 3.28084
    return {"capacity": capacity, "displacement": displacement,
            "volume": capacity * length if length > 0 else None,
            "metal_volume": displacement * length if length > 0 else None}


QUICK_CALC = Contract(
    stable_id="w13.volume.quick_calc", calculator="Volume › Quick Calc", schema_version=1,
    method_id="w13.volume.pipe_capacity", method_version="M73 pipe capacity v1",
    inputs=(FieldSpec("od", "OD", "in"), FieldSpec("id", "ID", "in"), FieldSpec("length", "Length", "m")),
    results=(FieldSpec("capacity", "Capacity", "bbl/m", 5), FieldSpec("displacement", "Displacement", "bbl/m", 5),
             FieldSpec("volume", "Volume", "bbl", 2), FieldSpec("metal_volume", "Metal Volume", "bbl", 2)),
    recalculate=_quick_calc,
    reference="capacity = ID^2 / 1029.4 bbl/ft (oilfield units); displacement = (OD^2 - ID^2) / 1029.4 bbl/ft",
)

CONTRACTS: Dict[str, Contract] = {QUICK_CALC.calculator: QUICK_CALC}
# method_id -> versions this build can still run. A version removed from here
# makes its stored cases NOT REPRODUCIBLE (never silently re-run with another method).
AVAILABLE_METHODS: Dict[str, Tuple[str, ...]] = {QUICK_CALC.method_id: (QUICK_CALC.method_version,)}


def contract_for(calculator: Optional[str]) -> Optional[Contract]:
    return CONTRACTS.get(str(calculator or ""))


def _by_method(method_id: str) -> Optional[Contract]:
    return next((c for c in CONTRACTS.values() if c.method_id == method_id), None)


def _norm(label: str) -> str:
    return re.sub(r"[\s:]+$", "", str(label or "")).strip().lower()


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    match = re.match(r"\s*([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)", str(value or ""))
    return float(match.group(1)) if match else None


def annotate(contract: Contract, inputs: Dict[str, Any],
             results: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    """Add ``field_id``/``unit`` to captured entries matched by label.

    Returns copies plus the contract fields that were not found on the page
    (the case is still stored; those fields are named, never invented).
    """
    def bind(entries: Dict[str, Any], specs: Tuple[FieldSpec, ...]) -> Tuple[Dict[str, Any], List[str]]:
        out = {key: dict(value) if isinstance(value, dict) else {"value": value} for key, value in entries.items()}
        by_label = {_norm(v.get("label", "")): key for key, v in out.items()}
        missing = []
        for spec in specs:
            key = by_label.get(_norm(spec.label))
            if key is None:
                missing.append(spec.field_id)
                continue
            out[key].update(field_id=spec.field_id, unit=spec.unit)
        return out, missing

    new_inputs, missing_inputs = bind(inputs, contract.inputs)
    new_results, _missing_results = bind(results, contract.results)   # results may legitimately be blank
    return new_inputs, new_results, missing_inputs


def _field_values(entries: Dict[str, Any]) -> Dict[str, Any]:
    return {v["field_id"]: v.get("value") for v in entries.values() if isinstance(v, dict) and v.get("field_id")}


def reproducibility(method_id: str, method_version: str) -> Tuple[str, str]:
    from core.calculation_cases import W13_UNVERSIONED

    if not method_version or method_version == W13_UNVERSIONED:
        return "NOT REPRODUCIBLE", "captured without a method version (before M73)"
    if _by_method(method_id) is None:
        return "NOT REPRODUCIBLE", f"no contract for method {method_id!r}"
    if method_version not in AVAILABLE_METHODS.get(method_id, ()):
        return "NOT REPRODUCIBLE", f"method version {method_version!r} is no longer available"
    return "REPRODUCIBLE", "contract method available"


def verify_case(method_id: str, method_version: str, inputs: Dict[str, Any],
                results: Dict[str, Any]) -> Dict[str, Any]:
    """Re-run a contract case with the current method and classify it.

    MATCH / DIFFERENT per the display-rounding tolerance (a result the case
    never stored is listed in ``not_compared``); NOT_REPRODUCIBLE when
    the method or version is unavailable; UNREADABLE when inputs are missing.
    """
    status, why = reproducibility(method_id, method_version)
    blank = {"method_matches": None, "current_method": "", "values": {}, "differences": [], "not_compared": []}
    if status != "REPRODUCIBLE":
        return {**blank, "status": "NOT_REPRODUCIBLE", "detail": f"{why}; reopen it in its calculator instead."}
    contract = _by_method(method_id)
    stored_inputs = _field_values(inputs)
    values: Dict[str, float] = {}
    for spec in contract.inputs:
        number = _number(stored_inputs.get(spec.field_id))
        if number is None:
            return {**blank, "status": "UNREADABLE", "detail": f"input {spec.field_id} is missing or not a number"}
        values[spec.field_id] = number
    try:
        current = contract.recalculate(values)
    except ValueError as exc:
        return {**blank, "status": "UNREADABLE", "detail": f"inputs rejected by the method: {exc}"}
    stored = _field_values(results)
    differences, not_compared = [], []
    for spec in contract.results:
        new, old = current.get(spec.field_id), _number(stored.get(spec.field_id))
        if new is None and old is None:
            continue
        if old is None:            # never stored with the case: named, not judged
            not_compared.append(spec.field_id)
            continue
        tolerance = 0.5 * 10 ** -(spec.decimals if spec.decimals is not None else 9)
        if new is None or old is None or abs(new - old) > tolerance:
            differences.append({"field_id": spec.field_id, "unit": spec.unit, "stored": old, "current": new,
                                "tolerance": tolerance})
    return {"status": "DIFFERENT" if differences else "MATCH", "method_matches": True,
            "current_method": f"{contract.method_id} {contract.method_version}",
            "detail": (f"{len(differences)} result(s) outside display rounding" if differences
                       else "stored results within display rounding")
                      + (f"; not stored, not compared: {', '.join(not_compared)}" if not_compared else ""),
            "values": {k: v for k, v in current.items() if v is not None}, "differences": differences,
            "not_compared": not_compared}
