"""M328 — Calculation History replay adapters for M314, M317 and M318 saved cases.

A replay re-runs the CURRENT method on the immutable input snapshot stored with the case and compares every stored
result field with the fresh one. It never re-reads the mutable source (the daily report, the cement report, W13
widgets): the snapshot is the record of what was computed.

Outcome vocabulary (shared with Calculation History):

* ``MATCH``            – every stored field equals the fresh field within its tolerance;
* ``DIFFERENT``        – at least one field differs (listed with stored / current / tolerance / unit);
* ``NOT_REPRODUCIBLE`` – the case cannot be replayed (method version not available in this build, case saved before
  M328 without a snapshot, the frozen architecture revision cannot be read here);
* ``UNREADABLE``       – the stored snapshot or result is malformed or fails its integrity (SHA-256) check.

Field tolerances are absolute and per unit (``FIELD_TOLERANCES``); text / status fields compare exactly. Tolerances
cover floating-point repeatability only. The M314 ±5 % HSI band is an engineering display band and is NOT used here.

Nothing is written by ``verify``; ``save_rerun`` stores a NEW case linked ``rerun_of`` the original.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Tuple

REPLAY_VERSION = "M328 v1"

# unit -> absolute tolerance (repeatability, not engineering acceptance)
FIELD_TOLERANCES: Dict[str, float] = {
    "gpm": 1e-6, "psi": 0.01, "hp": 0.01, "hp/in²": 0.001, "ft/s": 0.01, "lbf": 0.1, "bbl": 0.001, "%": 0.01,
    "m": 0.001, "klbf": 0.001, "ft·lbf": 0.1, "": 1e-9,
    "ppg": 1e-4, "in²": 1e-6, "ft/min": 0.01,                       # M366
    "in": 1e-6, "ft/h": 0.01, "psi/bbl": 1e-4,                       # M371 / M372 / M373 (M388: every unit listed)
    "psi/ft": 1e-6, "ft/h/klbf": 1e-6, "cP": 1e-6, "deg": 1e-9,      # M416 / M420 / M422 / M423
}


def _unit_of(method: str, key: str) -> str:
    """Unit of a stored result field, from the field name conventions of each method (never guessed)."""
    if method == "m314.ddr_bit_hydraulics_check":
        for suffix, unit in (("_flow_gpm", "gpm"), ("_pressure_drop_psi", "psi"), ("_hhp", "hp"), ("_hsi", "hp/in²"),
                             ("_jet_velocity_fps", "ft/s"), ("_impact_force_lbs", "lbf")):
            if key.endswith(suffix):
                return unit
        return ""
    if method == "m317.cement_job_reconciliation":
        return {"pumped_bbl": "bbl", "gauge_bbl": "bbl", "capacity_to_shoe_bbl": "bbl",
                "implied_excess_pct": "%"}.get(key, "")
    if method == "m318.td_friction_sensitivity":
        from core.torque_drag_sensitivity import CURVES

        for curve, (_engine_key, unit) in CURVES.items():
            if key.endswith(f"_{curve}"):
                return "ft·lbf" if unit in ("ft-lbf", "ft·lbf", "ft-lb") else unit
        return ""
    if method == "m366.hydraulics_workflow":
        from core.hydraulics_workflow import unit_of

        return unit_of(key)
    if method == "m368.survey_plan_deviation":
        from core.survey_plan_deviation import unit_of as m368_unit_of

        return m368_unit_of(key)
    if method == "m371.casing_axial_loads":
        from core.casing_axial_loads import unit_of as m371_unit_of

        return m371_unit_of(key)
    if method == "m372.mse_drilloff":
        from core.mse_drilloff import unit_of as m372_unit_of

        return m372_unit_of(key)
    if method == "m373.volumetric_method":
        from core.well_control_volumetric import unit_of as m373_unit_of

        return m373_unit_of(key)
    if method in SERVICE_MODULES:
        import importlib

        return importlib.import_module(SERVICE_MODULES[method][0]).unit_of(key)
    return ""


def _value(entry: Any) -> Any:
    return entry.get("value") if isinstance(entry, dict) else entry


def _input(inputs: Dict[str, Any], key: str) -> Any:
    return _value(inputs.get(key))


def compare(method: str, stored: Dict[str, Any], fresh: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every field on either side: numeric within its unit tolerance, text exactly, one-sided fields listed."""
    differences: List[Dict[str, Any]] = []
    for key in sorted(set(stored) | set(fresh)):
        unit = _unit_of(method, key)
        tolerance = FIELD_TOLERANCES.get(unit, FIELD_TOLERANCES[""])
        if key not in stored or key not in fresh:
            differences.append({"field_id": key, "stored": _value(stored.get(key)), "current": _value(fresh.get(key)),
                                "unit": unit, "tolerance": tolerance,
                                "reason": "only in the stored case" if key in stored else "only in the replay"})
            continue
        a, b = _value(stored[key]), _value(fresh[key])
        numeric = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (a, b))
        if numeric:
            if not (math.isfinite(a) and math.isfinite(b)) or abs(a - b) > tolerance:
                differences.append({"field_id": key, "stored": a, "current": b, "unit": unit, "tolerance": tolerance,
                                    "reason": f"differs by {abs(a - b):g} {unit}".rstrip()})
        elif a != b:
            differences.append({"field_id": key, "stored": a, "current": b, "unit": unit, "tolerance": None,
                                "reason": "text differs"})
    return differences


def _outcome(status: str, detail: str, current: str, *, values=None, differences=None,
             method_matches=None) -> Dict[str, Any]:
    return {"status": status, "detail": detail, "current_method": current, "method_matches": method_matches,
            "values": values or {}, "differences": differences or [], "not_compared": [],
            "replay_version": REPLAY_VERSION}


# ---- M314 ---------------------------------------------------------------------------------------------------
def _m314_current() -> str:
    from core import ddr_hydraulics_check as hc

    return f"{hc.METHOD_ID} {hc.METHOD_VERSION}"


def _m314_reproducible(inputs: Dict[str, Any], version: str) -> Tuple[str, str]:
    from core import ddr_hydraulics_check as hc

    if version != hc.METHOD_VERSION:
        return "NOT REPRODUCIBLE", f"hydraulics check version {version!r} is not available in this build"
    if not isinstance(_input(inputs, "snapshot"), dict):
        return "NOT REPRODUCIBLE", "the case was saved before M328 and holds no frozen input snapshot"
    return "REPRODUCIBLE", "re-run from the frozen gathered DDR inputs (the daily report is not re-read)"


def _m314_replay(db, inputs: Dict[str, Any], version: str) -> Dict[str, Any]:
    from core import ddr_hydraulics_check as hc

    snapshot = _input(inputs, "snapshot")
    if not isinstance(snapshot.get("inputs"), dict):
        raise ValueError("the frozen snapshot has no gathered inputs")
    if not isinstance(snapshot.get("problems"), list):
        raise ValueError("the frozen snapshot has no list of gathering problems")
    data = {"inputs": snapshot["inputs"], "problems": list(snapshot["problems"]),
            "report_id": snapshot.get("report_id"), "well_id": snapshot.get("well_id"),
            "drilling_parameters_id": snapshot.get("drilling_parameters_id")}
    result = hc.evaluate(data)
    return hc.case_results(result)


# ---- M317 ---------------------------------------------------------------------------------------------------
def _m317_current() -> str:
    from core import cement_job_reconciliation as cj

    return f"{cj.METHOD_ID} {cj.METHOD_VERSION}"


def _m317_reproducible(inputs: Dict[str, Any], version: str) -> Tuple[str, str]:
    from core import cement_job_reconciliation as cj

    if version != cj.METHOD_VERSION:
        return "NOT REPRODUCIBLE", f"cement reconciliation version {version!r} is not available in this build"
    missing = [k for k in ("job_snapshot", "architecture_revision_id", "components_sha256", "string")
               if _input(inputs, k) in (None, "")]
    if missing:
        return "NOT REPRODUCIBLE", f"the case does not record {', '.join(missing)}"
    return "REPRODUCIBLE", "re-run from the frozen recorded job and the SHA-256-checked architecture revision"


def _m317_replay(db, inputs: Dict[str, Any], version: str) -> Dict[str, Any]:
    from core import cement_job_reconciliation as cj
    from core import well_architecture as wa

    if db is None:
        raise LookupError("the architecture revision cannot be read here")
    revision = wa.get_revision(db, int(_input(inputs, "architecture_revision_id")))   # SHA-256 checked
    if revision["components_sha256"] != _input(inputs, "components_sha256"):
        raise wa.ArchitectureError("the architecture revision is not the one the case used (SHA-256 differs)")
    job = _input(inputs, "job_snapshot")
    if not isinstance(job, dict):
        raise ValueError("the frozen recorded job is not a mapping")
    result = cj.compute(dict(job), revision, _input(inputs, "string"), yield_unit=_input(inputs, "yield_unit"),
                        open_hole_in=_input(inputs, "open_hole_in"), caliper_in=_input(inputs, "caliper_in"))
    if result.get("status") != "COMPUTED":
        raise ValueError(f"the replay computed nothing: {result.get('reason') or result.get('status')}")
    return cj.case_payload(result)[1]


# ---- M318 ---------------------------------------------------------------------------------------------------
def _m318_current() -> str:
    from core import torque_drag_sensitivity as tds

    return f"{tds.METHOD_ID} {tds.METHOD_VERSION}"


def _m318_reproducible(inputs: Dict[str, Any], version: str) -> Tuple[str, str]:
    from core import torque_drag_sensitivity as tds

    if version not in tds.SUPPORTED_VERSIONS:
        return "NOT REPRODUCIBLE", f"T&D sensitivity version {version!r} is not available in this build"
    if not isinstance(_input(inputs, "run_snapshot"), dict):
        return "NOT REPRODUCIBLE", "the case was saved before M328 and holds no frozen run snapshot"
    if not _input(inputs, "survey_revision_id"):
        return "NOT REPRODUCIBLE", "the case is not tied to a pinned survey revision"
    return "REPRODUCIBLE", "re-run from the frozen survey stations and string after their SHA-256 checks"


class SnapshotIntegrityError(ValueError):
    """A frozen snapshot fails its own SHA-256 check (reported as UNREADABLE)."""


def _m318_replay(db, inputs: Dict[str, Any], version: str) -> Dict[str, Any]:
    from core import survey_revisions as sr
    from core import torque_drag_sensitivity as tds

    snap = _input(inputs, "run_snapshot")
    pin = snap.get("survey_source") or {}
    if sr.stations_sha256(snap.get("survey") or []) != pin.get("stations_sha256") \
            or pin.get("stations_sha256") != _input(inputs, "survey_stations_sha256"):
        raise SnapshotIntegrityError("the frozen survey stations fail their SHA-256 check")
    if tds.components_sha256(snap.get("components") or []) != snap.get("components_sha256"):
        raise SnapshotIntegrityError("the frozen drill-string components fail their SHA-256 check")
    result = tds.sweep(snap, _input(inputs, "friction_factors") or [], version=version)   # D92: as it was saved
    observations = {curve: _input(inputs, f"observed_{curve}") for curve in tds.CURVES}
    return tds.case_payload(result, observations)[1]


# ---- M366 ---------------------------------------------------------------------------------------------------
def _m366_current() -> str:
    from core import hydraulics_workflow as hw

    return f"{hw.METHOD_ID} {hw.METHOD_VERSION}"


def _m366_reproducible(inputs: Dict[str, Any], version: str) -> Tuple[str, str]:
    from core import hydraulics_workflow as hw

    if version not in hw.REPLAYABLE_VERSIONS:
        return "NOT REPRODUCIBLE", f"hydraulics workflow version {version!r} is not available in this build"
    if not isinstance(_input(inputs, "snapshot"), dict):
        return "NOT REPRODUCIBLE", "the case holds no frozen hydraulics snapshot"
    return "REPRODUCIBLE", "re-run from the frozen W13 hydraulics inputs after their SHA-256 check"


def _m366_replay(db, inputs: Dict[str, Any], version: str) -> Dict[str, Any]:
    from core import hydraulics_workflow as hw

    try:
        return hw.replay_results(inputs, version)
    except hw.IntegrityError as exc:
        raise SnapshotIntegrityError(str(exc)) from exc


# ---- M368 ---------------------------------------------------------------------------------------------------
def _m368_current() -> str:
    from core import survey_plan_deviation as spd

    return f"{spd.METHOD_ID} {spd.METHOD_VERSION}"


def _m368_reproducible(inputs: Dict[str, Any], version: str) -> Tuple[str, str]:
    from core import survey_plan_deviation as spd

    if version != spd.METHOD_VERSION:
        return "NOT REPRODUCIBLE", f"survey-vs-plan deviation version {version!r} is not available in this build"
    if not isinstance(_input(inputs, "snapshot"), dict):
        return "NOT REPRODUCIBLE", "the case holds no frozen survey/plan snapshot"
    return "REPRODUCIBLE", "re-run from the frozen survey and plan stations after their SHA-256 check"


def _m368_replay(db, inputs: Dict[str, Any], version: str) -> Dict[str, Any]:
    from core import survey_plan_deviation as spd

    try:
        return spd.replay_results(inputs)
    except spd.IntegrityError as exc:
        raise SnapshotIntegrityError(str(exc)) from exc


# ---- M371 ---------------------------------------------------------------------------------------------------
def _m371_current() -> str:
    from core import casing_axial_loads as cal

    return f"{cal.METHOD_ID} {cal.METHOD_VERSION}"


def _m371_reproducible(inputs: Dict[str, Any], version: str) -> Tuple[str, str]:
    from core import casing_axial_loads as cal

    if version != cal.METHOD_VERSION:
        return "NOT REPRODUCIBLE", f"casing axial-load version {version!r} is not available in this build"
    if not isinstance(inputs.get("inputs_sha256"), dict):
        return "NOT REPRODUCIBLE", "the case holds no inputs SHA-256"
    return "REPRODUCIBLE", "re-run from the stored declared inputs after their SHA-256 check"


def _m371_replay(db, inputs: Dict[str, Any], version: str) -> Dict[str, Any]:
    from core import casing_axial_loads as cal

    try:
        return cal.replay_results(inputs)
    except cal.IntegrityError as exc:
        raise SnapshotIntegrityError(str(exc)) from exc


# ---- M372 ---------------------------------------------------------------------------------------------------
def _m372_current() -> str:
    from core import mse_drilloff as mdo

    return f"{mdo.METHOD_ID} {mdo.METHOD_VERSION}"


def _m372_reproducible(inputs: Dict[str, Any], version: str) -> Tuple[str, str]:
    from core import mse_drilloff as mdo

    if version != mdo.METHOD_VERSION:
        return "NOT REPRODUCIBLE", f"drill-off version {version!r} is not available in this build"
    if not isinstance(inputs.get("inputs_sha256"), dict):
        return "NOT REPRODUCIBLE", "the case holds no inputs SHA-256"
    return "REPRODUCIBLE", "re-run from the stored declared inputs and steps after their SHA-256 check"


def _m372_replay(db, inputs: Dict[str, Any], version: str) -> Dict[str, Any]:
    from core import mse_drilloff as mdo

    try:
        return mdo.replay_results(inputs)
    except mdo.IntegrityError as exc:
        raise SnapshotIntegrityError(str(exc)) from exc


# ---- M373 ---------------------------------------------------------------------------------------------------
def _m373_current() -> str:
    from core import well_control_volumetric as wcv

    return f"{wcv.METHOD_ID} {wcv.METHOD_VERSION}"


def _m373_reproducible(inputs: Dict[str, Any], version: str) -> Tuple[str, str]:
    from core import well_control_volumetric as wcv

    if version != wcv.METHOD_VERSION:
        return "NOT REPRODUCIBLE", f"volumetric-method version {version!r} is not available in this build"
    if not isinstance(inputs.get("inputs_sha256"), dict):
        return "NOT REPRODUCIBLE", "the case holds no inputs SHA-256"
    return "REPRODUCIBLE", "re-run from the stored declared inputs after their SHA-256 check"


def _m373_replay(db, inputs: Dict[str, Any], version: str) -> Dict[str, Any]:
    from core import well_control_volumetric as wcv

    try:
        return wcv.replay_results(inputs)
    except wcv.IntegrityError as exc:
        raise SnapshotIntegrityError(str(exc)) from exc


# ---- M416 / M420 / M423 / M427 / M475: SHA-checked declared-input services (one generic adapter) ---------------------------
#: method id -> (module, description used in the NOT REPRODUCIBLE reason)
SERVICE_MODULES: Dict[str, Tuple[str, str]] = {
    "m416.hb_slot_annulus": ("core.hydraulics_hb_slot", "Herschel-Bulkley slot annulus"),
    "m420.surge_swab": ("core.surge_swab", "surge/swab"),
    "m423.drilloff_fitted": ("core.drilloff_fitted", "fitted drill-off"),
    "m427.bit_dull_grade": ("core.bit_dull_grade", "IADC dull grade record"),
    "m475.drilloff_robust": ("core.drilloff_robust", "robust (L1) drill-off"),
}


def _service_adapter(method: str) -> Tuple[Callable, Callable, Callable]:
    import importlib

    module_name, what = SERVICE_MODULES[method]

    def module():
        return importlib.import_module(module_name)

    def current() -> str:
        mod = module()
        return f"{mod.METHOD_ID} {mod.METHOD_VERSION}"

    def reproducible(inputs: Dict[str, Any], version: str) -> Tuple[str, str]:
        if version != module().METHOD_VERSION:
            return "NOT REPRODUCIBLE", f"{what} version {version!r} is not available in this build"
        if not isinstance(inputs.get("inputs_sha256"), dict):
            return "NOT REPRODUCIBLE", "the case holds no inputs SHA-256"
        return "REPRODUCIBLE", "re-run from the stored declared inputs after their SHA-256 check"

    def replay(db, inputs: Dict[str, Any], version: str) -> Dict[str, Any]:
        mod = module()
        try:
            return mod.replay_results(inputs)
        except mod.IntegrityError as exc:
            raise SnapshotIntegrityError(str(exc)) from exc

    return reproducible, replay, current


ADAPTERS: Dict[str, Tuple[Callable, Callable, Callable]] = {
    "m314.ddr_bit_hydraulics_check": (_m314_reproducible, _m314_replay, _m314_current),
    "m317.cement_job_reconciliation": (_m317_reproducible, _m317_replay, _m317_current),
    "m318.td_friction_sensitivity": (_m318_reproducible, _m318_replay, _m318_current),
    "m366.hydraulics_workflow": (_m366_reproducible, _m366_replay, _m366_current),
    "m368.survey_plan_deviation": (_m368_reproducible, _m368_replay, _m368_current),
    "m371.casing_axial_loads": (_m371_reproducible, _m371_replay, _m371_current),
    "m372.mse_drilloff": (_m372_reproducible, _m372_replay, _m372_current),
    "m373.volumetric_method": (_m373_reproducible, _m373_replay, _m373_current),
    **{method: _service_adapter(method) for method in SERVICE_MODULES},
}


def handles(method: Optional[str]) -> bool:
    return method in ADAPTERS


def reproducibility(method: str, inputs: Dict[str, Any], version: str) -> Tuple[str, str]:
    if not isinstance(inputs, dict):
        return "NOT REPRODUCIBLE", "the stored inputs are not readable"
    return ADAPTERS[method][0](inputs, version)


def verify(db, method: str, inputs: Dict[str, Any], results: Dict[str, Any], version: str) -> Dict[str, Any]:
    """Replay one saved case; never raises for a bad record (reported UNREADABLE / NOT_REPRODUCIBLE)."""
    from core import well_architecture as wa

    check, replay, current_of = ADAPTERS[method]
    current = current_of()
    status, why = reproducibility(method, inputs, version)
    if status != "REPRODUCIBLE":
        return _outcome("NOT_REPRODUCIBLE", why, current)
    if not isinstance(results, dict) or not all(isinstance(v, dict) for v in results.values()):
        return _outcome("UNREADABLE", "the stored result is not a case payload; it is shown as saved", current)
    try:
        fresh = replay(db, inputs, version)
    except KeyError as exc:                         # a KeyError is a LookupError: a malformed snapshot, not a miss
        return _outcome("UNREADABLE", f"the frozen snapshot lacks the field {exc}; nothing was recomputed", current)
    except LookupError as exc:
        return _outcome("NOT_REPRODUCIBLE", f"{exc}; the stored result is shown as saved", current)
    except (SnapshotIntegrityError, wa.ArchitectureError) as exc:
        return _outcome("UNREADABLE", f"{exc}; nothing was recomputed", current)
    except (TypeError, ValueError, AttributeError) as exc:
        return _outcome("UNREADABLE", f"the frozen snapshot could not be replayed ({type(exc).__name__}: {exc})",
                        current)
    differences = compare(method, results, fresh)
    return _outcome("DIFFERENT" if differences else "MATCH",
                    f"{len(differences)} field(s) differ" if differences else
                    f"all {len(fresh)} field(s) match within their tolerances",
                    current, values=fresh, differences=differences, method_matches=True)


def save_rerun(db, entry, outcome: Dict[str, Any], user_id: Optional[int] = None) -> Dict[str, Any]:
    """Store a replay as a NEW case linked ``rerun_of`` the original; the original is never written."""
    from core import calculation_cases as cc

    if outcome.get("status") not in ("MATCH", "DIFFERENT") or not outcome.get("values"):
        raise ValueError(f"Nothing to store: replay status {outcome.get('status')}.")
    return cc.save_case(
        db, calculator=f"{entry.source} replay", name=f"{entry.name} (replay)", inputs=entry.inputs,
        results=outcome["values"], method=entry.method, method_version=entry.version, well_id=entry.well_id,
        wellbore_id=entry.wellbore_id, user_id=user_id,
        note=f"{REPLAY_VERSION} replay of case #{entry.record_id} from its frozen snapshot: {outcome['status']}",
        source_link={"link_type": "rerun_of", "source_table": entry.table, "source_id": entry.record_id,
                     "source_method": entry.method, "source_method_version": entry.version,
                     "recalc_method": entry.method, "recalc_method_version": entry.version,
                     "verification_status": outcome["status"], "method_changed": False})
