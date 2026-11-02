"""M62: persistent, versioned directional plans (``DirectionalPlanRevision``).

A plan is identified by ``plan_key``; every save is a new immutable revision
(``revision`` 1, 2, ...) with ``parent_id`` pointing at the revision it was
derived from. Inputs (segments, tie-in, targets, step, DLS limit, VS azimuth)
and results (stations, segments, warnings, targets) are stored together with
the designer method and version that produced them. Only ``status`` changes
afterwards (M70: enforced by ``PLAN_LIFECYCLE`` and a storage trigger). Sessions stay inside this module; callers receive plain dicts.
"""

from __future__ import annotations

import csv
import hashlib
import json
import uuid
from typing import Any, Dict, List, Optional

from core.well_plan_designer import METHOD, PLAN_VERSION, PlanResult, design_plan

STATUSES = ("draft", "approved", "archived")
STATION_COLUMNS = ("md", "inc", "azi", "tvd", "north", "east", "vs", "dls")


def plan_inputs(segments, *, tie_in=None, targets=(), step=30.0, dls_limit=None, vs_azimuth=0.0) -> Dict[str, Any]:
    return json.loads(json.dumps({
        "segments": list(segments), "tie_in": dict(tie_in or {}), "targets": list(targets),
        "step": step, "dls_limit": dls_limit, "vs_azimuth": vs_azimuth,
    }))


def run_inputs(inputs: Dict[str, Any]) -> PlanResult:
    return design_plan(inputs["segments"], step=inputs.get("step", 30.0), dls_limit=inputs.get("dls_limit"),
                       vs_azimuth=inputs.get("vs_azimuth", 0.0), targets=inputs.get("targets", ()),
                       tie_in=inputs.get("tie_in") or None)


def _results(result: PlanResult) -> Dict[str, Any]:
    return json.loads(json.dumps({
        "stations": result.stations, "segments": result.segments, "targets": result.targets,
        "warnings": result.warnings,
    }))


def _dto(row) -> Dict[str, Any]:
    return {
        "id": row.id, "well_id": row.well_id, "wellbore_id": row.wellbore_id, "plan_key": row.plan_key,
        "name": row.name, "revision": row.revision, "parent_id": row.parent_id, "status": row.status,
        "method": row.method, "method_version": row.method_version, "inputs": row.inputs or {},
        "results": row.results or {}, "note": row.note or "",
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class PlanIntegrityError(ValueError):
    """A save/revise/status request that would break plan integrity (explicit message)."""


class StaleRevisionError(PlanIntegrityError):
    """The revision being revised is no longer the latest, or a concurrent save won the race."""


def result_fingerprint(results: Dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON of a stored results dict (without its own fingerprint)."""
    body = {k: v for k, v in (results or {}).items() if k != "result_sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _trusted_results(inputs: Dict[str, Any], supplied: Optional[PlanResult]) -> tuple[PlanResult, Dict[str, Any]]:
    """Recompute from the exact inputs that will be stored; a supplied result must be identical.

    The trusted service boundary never stores a caller's result as-is: the
    stored results are always the designer's output for the stored inputs.
    """
    result = run_inputs(inputs)
    if not result.ok:
        raise PlanIntegrityError(f"The plan is not valid and was not saved: {result.error}")
    results = _results(result)
    if supplied is not None:
        if (supplied.version or PLAN_VERSION) != (result.version or PLAN_VERSION):
            raise PlanIntegrityError("The supplied result was produced by another designer version; redesign first.")
        if result_fingerprint(_results(supplied)) != result_fingerprint(results):
            raise PlanIntegrityError(
                "The supplied result does not correspond to the inputs being saved; redesign before saving.")
    results["result_sha256"] = result_fingerprint(results)
    return result, results


def _audit(db, action: str, revision_id, details: str) -> None:
    log = getattr(db, "log_audit", None)
    if callable(log):
        log(action, entity_type="directional_plan_revision", entity_id=revision_id, details=details)


def _check_wellbore(session, well_id: int, wellbore_id: Optional[int]) -> None:
    from core.database import Well, Wellbore

    if session.get(Well, well_id) is None:
        raise PlanIntegrityError(f"Well {well_id} does not exist.")
    if wellbore_id is not None:
        bore = session.get(Wellbore, wellbore_id)
        if bore is None or bore.well_id != well_id:
            raise PlanIntegrityError(f"Wellbore {wellbore_id} does not belong to well {well_id}.")


def _check_survey_tie_in(session, well_id: int, wellbore_id: Optional[int], tie_in: Dict[str, Any]) -> None:
    """M72: a tie-in pinned to a survey revision must match that revision exactly."""
    from core.database import SurveyRevision

    revision_id = tie_in.get("survey_revision_id")
    if revision_id is None:
        return
    row = session.get(SurveyRevision, int(revision_id))
    if row is None or row.well_id != well_id:
        raise PlanIntegrityError(f"Survey revision {revision_id} does not belong to well {well_id}.")
    if wellbore_id is not None and row.wellbore_id is not None and row.wellbore_id != wellbore_id:
        raise PlanIntegrityError(f"Survey revision {revision_id} is on another wellbore.")
    if tie_in.get("survey_sha256") != row.stations_sha256:
        raise PlanIntegrityError(f"The tie-in does not match the stations of survey revision {revision_id}.")
    missing = [k for k in ("md", "inc", "azi", "tvd", "north", "east") if tie_in.get(k) is None]
    if missing:
        raise PlanIntegrityError(f"The survey tie-in lacks {', '.join(missing)}.")
    stations = json.loads(row.results_json)
    station = next((s for s in stations if abs(s["md"] - float(tie_in.get("md", -1))) <= 1e-6), None)
    if station is None or any(abs(float(tie_in.get(k, float("nan"))) - station[k]) > 1e-6
                              for k in ("inc", "tvd", "north", "east")) or \
            abs(((float(tie_in.get("azi", float("nan"))) - station["azi"] + 180.0) % 360.0) - 180.0) > 1e-6:
        raise PlanIntegrityError(f"The tie-in is not a station of survey revision {revision_id}.")


def save_plan(db, *, well_id: int, name: str, inputs: Dict[str, Any], result: Optional[PlanResult] = None,
              wellbore_id: Optional[int] = None, plan_key: Optional[str] = None, parent_id: Optional[int] = None,
              note: str = "", user_id: Optional[int] = None) -> Dict[str, Any]:
    """Insert a new revision. With ``plan_key`` it is the next revision of that plan.

    Integrity rules (M70): results are recomputed from ``inputs`` (a supplied
    ``result`` must match exactly); the wellbore belongs to the well; a parent
    exists and has the same well and wellbore; with ``plan_key`` the parent is
    that plan's latest revision (otherwise :class:`StaleRevisionError`); a
    concurrent save of the same revision number is reported, never merged.
    """
    from sqlalchemy.exc import IntegrityError

    from core.database import DirectionalPlanRevision

    if not str(name or "").strip():
        raise PlanIntegrityError("A plan name is required.")
    inputs = json.loads(json.dumps(inputs))
    result, results = _trusted_results(inputs, result)
    try:
        with db.session_scope() as session:
            _check_wellbore(session, well_id, wellbore_id)
            _check_survey_tie_in(session, well_id, wellbore_id, inputs.get("tie_in") or {})
            parent = session.get(DirectionalPlanRevision, parent_id) if parent_id is not None else None
            if parent_id is not None:
                if parent is None:
                    raise PlanIntegrityError(f"Parent revision {parent_id} does not exist.")
                if parent.well_id != well_id or parent.wellbore_id != wellbore_id:
                    raise PlanIntegrityError(
                        f"Parent revision {parent_id} belongs to well {parent.well_id} / wellbore "
                        f"{parent.wellbore_id}, not well {well_id} / wellbore {wellbore_id}.")
            if plan_key:
                lineage = (session.query(DirectionalPlanRevision)
                           .filter(DirectionalPlanRevision.plan_key == plan_key)
                           .order_by(DirectionalPlanRevision.revision.desc()).all())
                if not lineage:
                    raise PlanIntegrityError(f"Plan {plan_key} does not exist; save it as a new plan.")
                if any(r.well_id != well_id or r.wellbore_id != wellbore_id for r in lineage):
                    raise PlanIntegrityError("A plan cannot move to another well or wellbore; clone it instead.")
                if parent is None or parent.plan_key != plan_key:
                    raise PlanIntegrityError("A revision must name a parent revision of the same plan.")
                if parent.id != lineage[0].id:
                    raise StaleRevisionError(
                        f"Revision {parent.revision} is not the latest revision ({lineage[0].revision}) of "
                        f"{lineage[0].name}; open the latest revision before revising.")
                revision = _next_revision(session, plan_key)
            else:
                plan_key, revision = uuid.uuid4().hex, 1
            row = DirectionalPlanRevision(
                well_id=well_id, wellbore_id=wellbore_id, plan_key=plan_key, name=str(name).strip(),
                revision=revision, parent_id=parent_id, status="draft", method=result.method or METHOD,
                method_version=result.version or PLAN_VERSION, inputs=inputs, results=results,
                note=note, created_by=user_id,
            )
            session.add(row)
            session.flush()
            return _dto(row)
    except IntegrityError as exc:
        if "uq_directional_plan_revision" in str(exc) or "UNIQUE" in str(exc).upper():
            raise StaleRevisionError(
                "Another revision of this plan was saved at the same time; reopen the latest revision "
                "and save again.") from exc
        raise


def _next_revision(session, plan_key: str) -> int:
    from core.database import DirectionalPlanRevision

    latest = (session.query(DirectionalPlanRevision.revision)
              .filter(DirectionalPlanRevision.plan_key == plan_key)
              .order_by(DirectionalPlanRevision.revision.desc()).first())
    return (latest[0] if latest else 0) + 1


def revise_plan(db, revision_id: int, inputs: Dict[str, Any], *, note: str = "",
                user_id: Optional[int] = None, result: Optional[PlanResult] = None) -> Dict[str, Any]:
    """New revision of the same plan derived from ``revision_id`` (must be the latest); the old one is untouched."""
    parent = get_plan(db, revision_id)
    return save_plan(db, well_id=parent["well_id"], wellbore_id=parent["wellbore_id"], name=parent["name"],
                     inputs=inputs, result=result, plan_key=parent["plan_key"], parent_id=parent["id"],
                     note=note, user_id=user_id)


def clone_plan(db, revision_id: int, name: str, *, user_id: Optional[int] = None) -> Dict[str, Any]:
    """A new plan (new key, revision 1) starting from an existing revision's inputs (same well/wellbore)."""
    source = get_plan(db, revision_id)
    return save_plan(db, well_id=source["well_id"], wellbore_id=source["wellbore_id"], name=name,
                     inputs=source["inputs"], parent_id=source["id"],
                     note=f"Cloned from {source['name']} rev {source['revision']}", user_id=user_id)


def set_status(db, revision_id: int, status: str) -> Dict[str, Any]:
    """Lifecycle change (the only permitted update). Refusals are audited."""
    from core.authorization import PLAN_LIFECYCLE, operation_scope
    from core.database import DirectionalPlanRevision
    from core.storage_guards import PLAN_STATUS_TRANSITIONS

    if status not in STATUSES:
        _audit(db, "PLAN_STATUS_REJECTED", revision_id, f"unknown status {status!r}")
        raise PlanIntegrityError(f"Unknown plan status {status!r}; use one of {', '.join(STATUSES)}.")
    with operation_scope(PLAN_LIFECYCLE), db.session_scope() as session:
        row = session.get(DirectionalPlanRevision, revision_id)
        if row is None:
            raise LookupError(f"Plan revision {revision_id} does not exist.")
        if status not in PLAN_STATUS_TRANSITIONS.get(row.status, ()):
            old = row.status
            message = ("An archived revision stays archived; revise or clone it instead." if old == "archived"
                       else f"A plan revision cannot go from {old} to {status}.")
            _audit(db, "PLAN_STATUS_REJECTED", revision_id, f"{old} -> {status}")
            raise PlanIntegrityError(message)
        row.status = status
        session.flush()
        return _dto(row)


def get_plan(db, revision_id: int) -> Dict[str, Any]:
    from core.database import DirectionalPlanRevision

    with db.session_scope() as session:
        row = session.get(DirectionalPlanRevision, revision_id)
        if row is None:
            raise LookupError(f"Plan revision {revision_id} does not exist.")
        return _dto(row)


def list_plans(db, well_id: int, *, include_archived: bool = False) -> List[Dict[str, Any]]:
    """Every revision of the well's plans, newest revision first within each plan."""
    from core.database import DirectionalPlanRevision

    with db.session_scope() as session:
        query = session.query(DirectionalPlanRevision).filter(DirectionalPlanRevision.well_id == well_id)
        if not include_archived:
            query = query.filter(DirectionalPlanRevision.status != "archived")
        rows = query.order_by(DirectionalPlanRevision.name, DirectionalPlanRevision.plan_key,
                              DirectionalPlanRevision.revision.desc()).all()
        return [_dto(row) for row in rows]


def summary(plan: Dict[str, Any]) -> Dict[str, Any]:
    stations = (plan.get("results") or {}).get("stations") or []
    if not stations:
        return {"td_md": None, "td_tvd": None, "max_dls": None, "end_north": None, "end_east": None}
    last = stations[-1]
    return {"td_md": last["md"], "td_tvd": last["tvd"], "max_dls": max(s.get("dls", 0.0) for s in stations),
            "end_north": last["north"], "end_east": last["east"]}


def compare_plans(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Input differences and headline result differences between two revisions."""
    keys = sorted(set(a["inputs"]) | set(b["inputs"]))
    inputs = [{"input": k, "a": a["inputs"].get(k), "b": b["inputs"].get(k)}
              for k in keys if a["inputs"].get(k) != b["inputs"].get(k)]
    sa, sb = summary(a), summary(b)
    results = []
    for key in sa:
        va, vb = sa[key], sb[key]
        delta = (vb - va) if isinstance(va, (int, float)) and isinstance(vb, (int, float)) else None
        results.append({"quantity": key, "a": va, "b": vb, "delta": delta})
    return {"a": f"{a['name']} rev {a['revision']}", "b": f"{b['name']} rev {b['revision']}",
            "method_versions": (a["method_version"], b["method_version"]), "inputs": inputs, "results": results}


def export_plan_csv(plan: Dict[str, Any], path: str) -> None:
    stations = (plan.get("results") or {}).get("stations") or []
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([f"# plan {plan['name']} rev {plan['revision']} ({plan['status']}); "
                         f"{plan['method']}; {plan['method_version']}; planning aid, not validated"])
        writer.writerow(["MD (m)", "Inc (deg)", "Azi (deg)", "TVD (m)", "North (m)", "East (m)", "VS (m)",
                         "DLS (deg/30m)"])
        for station in stations:
            writer.writerow([f"{float(station.get(c, 0.0)):.4f}" for c in STATION_COLUMNS])


# ---- M70.4: whole-result verification -------------------------------------------------------
# Plans are designed in one unit system: lengths in metres, angles in degrees,
# DLS/build/turn in degrees per 30 m. A stored record that declares another
# unit system is not compared (NOT_REPRODUCIBLE). Tolerances are absolute, per
# quantity; the designer is deterministic, so they only absorb floating-point
# noise and never hide an engineering change:
#   * station/segment positions (md, tvd, north, east, vs, hd, length) 1e-6 m;
#   * angles (inc, azi) 1e-7 deg, azimuth compared on the circle (359.9999999 = 0);
#   * rates (dls, build_rate, turn_rate) 1e-7 deg/30 m;
#   * target closest-point MD and coordinates 1e-5 m (golden-section search to
#     1e-9 of a <=30 m interval, i.e. ~3e-8 m, plus margin), distances 1e-6 m;
#   * counts, names, types, hit/miss, radius and warnings must be identical.
PLAN_UNITS = {"length": "m", "angle": "deg", "rate": "deg/30m"}
PLAN_TOLERANCES = {
    "md": 1e-6, "tvd": 1e-6, "north": 1e-6, "east": 1e-6, "vs": 1e-6, "hd": 1e-6, "length": 1e-6,
    "start_md": 1e-6, "end_md": 1e-6, "inc": 1e-7, "azi": 1e-7, "dls": 1e-7, "build_rate": 1e-7,
    "turn_rate": 1e-7, "closest_md": 1e-5, "closest_station_md": 1e-5, "distance": 1e-6,
    "station_distance": 1e-6,
}
_POINT_TOL = 1e-5


def _number_differs(key: str, a, b, tol: float) -> bool:
    if isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return a != b
    if key == "azi":
        return abs(((float(a) - float(b) + 180.0) % 360.0) - 180.0) > tol
    return abs(float(a) - float(b)) > tol


def _compare_records(path: str, stored: Dict[str, Any], recalc: Dict[str, Any], out: list, *,
                     point_tol: Optional[float] = None) -> None:
    for key in sorted(set(stored) | set(recalc)):
        a, b = stored.get(key), recalc.get(key)
        where = f"{path}.{key}"
        if key not in stored or key not in recalc:
            out.append({"field": where, "stored": a, "recalculated": b, "tolerance": "present in both"})
        elif isinstance(a, dict) and isinstance(b, dict):
            _compare_records(where, a, b, out, point_tol=_POINT_TOL if key == "closest_point" else point_tol)
        else:
            tol = point_tol if point_tol is not None else PLAN_TOLERANCES.get(key, 0.0)
            if _number_differs(key, a, b, tol):
                out.append({"field": where, "stored": a, "recalculated": b,
                            "tolerance": tol if isinstance(a, (int, float)) and not isinstance(a, bool) else "exact"})


def compare_plan_results(stored: Dict[str, Any], recalculated: Dict[str, Any]) -> Dict[str, Any]:
    """Compare every station, segment, target and warning of two plan results.

    Returns ``status`` (``MATCH`` / ``DIFFERENT`` / ``UNREADABLE``), the list of
    ``differences`` (field, stored, recalculated, tolerance) and the number of
    ``checked`` records. A stored fingerprint that no longer matches its own
    stored results is ``UNREADABLE`` (the record was altered outside the app).
    """
    stored = stored or {}
    if not isinstance(stored.get("stations"), list) or not stored["stations"]:
        return {"status": "UNREADABLE", "differences": [], "checked": 0, "detail": "the stored plan has no stations"}
    fingerprint = stored.get("result_sha256")
    if fingerprint and fingerprint != result_fingerprint(stored):
        return {"status": "UNREADABLE", "differences": [], "checked": 0,
                "detail": "the stored results do not match their own fingerprint (altered outside DrillMaster)"}
    differences: list = []
    checked = 0
    for group in ("stations", "segments", "targets"):
        a, b = stored.get(group) or [], recalculated.get(group) or []
        if len(a) != len(b):
            differences.append({"field": f"{group}.count", "stored": len(a), "recalculated": len(b),
                                "tolerance": "exact"})
        for index, (ra, rb) in enumerate(zip(a, b)):
            _compare_records(f"{group}[{index}]", ra, rb, differences)
            checked += 1
    if list(stored.get("warnings") or []) != list(recalculated.get("warnings") or []):
        differences.append({"field": "warnings", "stored": stored.get("warnings") or [],
                            "recalculated": recalculated.get("warnings") or [], "tolerance": "exact"})
    return {"status": "DIFFERENT" if differences else "MATCH", "differences": differences, "checked": checked,
            "detail": f"{len(differences)} field(s) differ" if differences else f"{checked} records identical"}


def verify_plan_record(inputs: Dict[str, Any], stored_results: Dict[str, Any], stored_version: str) -> Dict[str, Any]:
    """Re-run a stored plan with the current designer and compare the whole result."""
    units = (inputs or {}).get("units")
    method_matches = stored_version == PLAN_VERSION
    base = {"current_method": PLAN_VERSION, "method_matches": method_matches, "stored_version": stored_version}
    if units not in (None, PLAN_UNITS):
        return dict(base, status="NOT_REPRODUCIBLE", differences=[], values={},
                    detail=f"stored plan declares units {units!r}; the designer uses {PLAN_UNITS}")
    try:
        result = run_inputs(inputs)
    except (KeyError, TypeError, ValueError) as exc:
        return dict(base, status="UNREADABLE", differences=[], values={}, detail=f"stored inputs unreadable: {exc}")
    if not result.ok:
        return dict(base, status="NOT_REPRODUCIBLE", differences=[], values={}, detail=result.error)
    recalculated = _results(result)
    comparison = compare_plan_results(stored_results, recalculated)
    detail = comparison["detail"] + ("" if method_matches else
                                     f"; METHOD CHANGED: stored {stored_version}, current {PLAN_VERSION}")
    recalculated["result_sha256"] = result_fingerprint(recalculated)
    return dict(base, status=comparison["status"], differences=comparison["differences"], detail=detail,
                values=recalculated)
