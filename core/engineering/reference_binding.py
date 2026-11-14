"""M184-M189: one shared service that binds a tubular library item to a module's input - and checks it later.

Contract ``tubular-binding-v1``. A *binding* is what a module stores next to its own values when the user picks
an item from the tubular reference library (Architecture string, Volumes / Hydraulics / Weight-T&D string
component, Casing strength):

``{"contract", "snapshot": <reference_snapshot>, "fields": {module_key: library_field, ...},
"unavailable": [module_key, ...]}``

* The snapshot is the immutable copy from :func:`core.engineering.tubular_reference.reference_snapshot` (full
  spec, set name / version / fingerprints). The module's result never depends on today's library.
* ``fields`` lists only the module values that were filled from the item. A library value that is unavailable is
  **not** filled - it is listed in ``unavailable`` and the module keeps treating it as unknown (never 0).
* A binding only describes a component while the bound values are unchanged: :func:`binding_holds` is checked
  before anything is stored, so an edited value is never presented as library data.
* :func:`drift` compares a stored snapshot with the library today: ``MATCH`` (the cited version is unchanged),
  ``DIFFERENT`` (the cited version or item no longer matches its fingerprint), ``NOT_REPRODUCIBLE`` (the cited
  version is not in this database - the snapshot itself stays valid) or ``UNREADABLE`` (the snapshot fails its
  own integrity check). Nothing is ever redrawn or recalculated from the library silently.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from core.engineering import tubular_reference as tr

CONTRACT_VERSION = "tubular-binding-v1"
MATCH, DIFFERENT, NOT_REPRODUCIBLE, UNREADABLE = "MATCH", "DIFFERENT", "NOT_REPRODUCIBLE", "UNREADABLE"
BINDING_KEY = "tubular_reference"
VALUE_TOLERANCE = 1e-9

# Module key -> library field, per consumer. Only geometry, weight and identity text: the library holds no yield
# strength and its pipe-body ratings are not connection ratings, so neither is ever filled into a calculation.
PIPE_COMPONENT_FIELDS = {"od": "nominal_od_in", "id": "id_in", "weight": "weight_ppf", "grade": "grade",
                         "connection": "connection", "tj_od": "tool_joint_od_in"}
CASING_STRENGTH_FIELDS = {"od_in": "nominal_od_in", "id_in": "id_in", "wall_in": "wall_in",
                          "weight_ppf": "weight_ppf"}
ARCHITECTURE_FIELDS = {"od_in": "nominal_od_in", "id_in": "id_in", "weight_ppf": "weight_ppf", "grade": "grade"}

# The AddPipeDialog component types the library can describe (the others have no library type).
PIPE_TYPE_TO_COMPONENT = {"Drill Pipe": "DP", "HWDP": "HWDP", "Drill Collar": "DC"}
STRING_KIND_TO_COMPONENT = {"casing": "CASING", "liner": "LINER", "tubing": "TUBING"}


class BindingError(ValueError):
    """The snapshot cannot be bound (tampered, unreadable, or nothing usable in it)."""


@dataclass(frozen=True)
class Drift:
    state: str
    message: str

    def to_dict(self) -> Dict[str, str]:
        return {"state": self.state, "message": self.message}


def values_from_snapshot(snapshot: Mapping[str, Any], mapping: Mapping[str, str]) -> Tuple[Dict[str, Any], List[str]]:
    """(module values that the item provides, module keys it leaves unavailable). Refuses a damaged snapshot."""
    problems = tr.verify_snapshot(snapshot)
    if problems:
        raise BindingError("The library snapshot is not intact: " + "; ".join(problems))
    spec = snapshot.get("spec") or {}
    values: Dict[str, Any] = {}
    unavailable: List[str] = []
    for key, library_field in mapping.items():
        value = spec.get(library_field)
        if value is None or (isinstance(value, str) and not value.strip()):
            unavailable.append(key)
        else:
            values[key] = value
    if not values:
        raise BindingError("The library item holds none of the values this input needs")
    return values, unavailable


def make_binding(snapshot: Mapping[str, Any], mapping: Mapping[str, str]) -> Dict[str, Any]:
    values, unavailable = values_from_snapshot(snapshot, mapping)
    return {"contract": CONTRACT_VERSION, "snapshot": json.loads(json.dumps(snapshot)),
            "fields": {key: mapping[key] for key in values}, "unavailable": unavailable}


def bound_values(binding: Mapping[str, Any]) -> Dict[str, Any]:
    spec = (binding.get("snapshot") or {}).get("spec") or {}
    return {key: spec.get(field) for key, field in (binding.get("fields") or {}).items()}


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) \
            and not isinstance(b, bool):
        return math.isfinite(a) and math.isfinite(b) and abs(float(a) - float(b)) <= VALUE_TOLERANCE
    return (str(a).strip() if a is not None else None) == (str(b).strip() if b is not None else None)


def edited_fields(binding: Mapping[str, Any], values: Mapping[str, Any]) -> List[str]:
    """Module keys whose current value no longer equals the bound library value.

    A key the module does not hold at all (e.g. a hydraulics row has no grade column) is not compared; a key it
    holds with another value - including a cleared one - is an edit.
    """
    return [key for key, expected in bound_values(binding).items()
            if key in values and not _same(values.get(key), expected)]


def binding_holds(binding: Optional[Mapping[str, Any]], values: Mapping[str, Any]) -> bool:
    return isinstance(binding, Mapping) and binding.get("contract") == CONTRACT_VERSION \
        and not edited_fields(binding, values)


def attach(component: Dict[str, Any], binding: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """``component`` with the binding when it still holds, otherwise without one (an edit drops it)."""
    out = {k: v for k, v in component.items() if k != BINDING_KEY}
    if binding_holds(binding, out):
        out[BINDING_KEY] = dict(binding)
    return out


def drift(db, snapshot: Optional[Mapping[str, Any]]) -> Drift:
    """Today's library against a stored snapshot (never changes the snapshot or the result)."""
    from core.database import TubularReferenceItem, TubularReferenceSet

    if not isinstance(snapshot, Mapping):
        return Drift(UNREADABLE, "No readable library snapshot is stored")
    problems = tr.verify_snapshot(snapshot)
    if problems:
        return Drift(UNREADABLE, "; ".join(problems))
    label = f"{snapshot.get('set_name')} v{snapshot.get('set_version')}"
    with db.session_scope() as session:
        ref = session.query(TubularReferenceSet).filter_by(name=snapshot.get("set_name"),
                                                           version=snapshot.get("set_version")).first()
        if ref is None:
            return Drift(NOT_REPRODUCIBLE, f"{label} is not in this database; the stored snapshot stays valid")
        if ref.status != tr.PUBLISHED or ref.content_fingerprint != snapshot.get("set_fingerprint"):
            return Drift(DIFFERENT, f"{label} no longer has the fingerprint it had when the value was taken")
        found = session.query(TubularReferenceItem).filter_by(
            set_id=ref.id, fingerprint=snapshot.get("item_fingerprint")).first()
        if found is None:
            return Drift(DIFFERENT, f"the cited item is not in {label}")
        newer = (session.query(TubularReferenceSet)
                 .filter(TubularReferenceSet.name == ref.name, TubularReferenceSet.version > ref.version,
                         TubularReferenceSet.status == tr.PUBLISHED).count())
    note = f"; {newer} newer published version(s) exist and are NOT applied" if newer else ""
    return Drift(MATCH, f"{label} unchanged{note}")


def find_bindings(value: Any, path: str = "") -> List[Tuple[str, Dict[str, Any]]]:
    """Every binding nested anywhere in a stored structure (case inputs, architecture components...)."""
    found: List[Tuple[str, Dict[str, Any]]] = []
    if isinstance(value, Mapping):
        if value.get("contract") == CONTRACT_VERSION and isinstance(value.get("snapshot"), Mapping):
            return [(path or "/", dict(value))]
        for key, child in value.items():
            found += find_bindings(child, f"{path}/{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            found += find_bindings(child, f"{path}/{index}")
    return found


def drift_report(db, value: Any) -> List[Dict[str, Any]]:
    out = []
    for path, binding in find_bindings(value):
        snapshot = binding.get("snapshot") or {}
        state = drift(db, snapshot)
        out.append({"path": path, "designation": (snapshot.get("spec") or {}).get("designation"),
                    "set": f"{snapshot.get('set_name')} v{snapshot.get('set_version')}", **state.to_dict()})
    return out


def summarize(report: Iterable[Mapping[str, Any]]) -> str:
    rows = list(report)
    if not rows:
        return ""
    counts: Dict[str, int] = {}
    for row in rows:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    return "Library references: " + ", ".join(f"{n} {state}" for state, n in sorted(counts.items()))
