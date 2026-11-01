"""M62: persistent, versioned directional plans (``DirectionalPlanRevision``).

A plan is identified by ``plan_key``; every save is a new immutable revision
(``revision`` 1, 2, ...) with ``parent_id`` pointing at the revision it was
derived from. Inputs (segments, tie-in, targets, step, DLS limit, VS azimuth)
and results (stations, segments, warnings, targets) are stored together with
the designer method and version that produced them. Only ``status`` changes
afterwards. Sessions stay inside this module; callers receive plain dicts.
"""

from __future__ import annotations

import csv
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


def save_plan(db, *, well_id: int, name: str, inputs: Dict[str, Any], result: Optional[PlanResult] = None,
              wellbore_id: Optional[int] = None, plan_key: Optional[str] = None, parent_id: Optional[int] = None,
              note: str = "", user_id: Optional[int] = None) -> Dict[str, Any]:
    """Insert a new revision. With ``plan_key`` it is the next revision of that plan."""
    from core.database import DirectionalPlanRevision

    if not str(name or "").strip():
        raise ValueError("A plan name is required.")
    result = result if result is not None else run_inputs(inputs)
    if not result.ok:
        raise ValueError(f"The plan is not valid and was not saved: {result.error}")
    with db.session_scope() as session:
        if plan_key:
            latest = (session.query(DirectionalPlanRevision.revision)
                      .filter(DirectionalPlanRevision.plan_key == plan_key)
                      .order_by(DirectionalPlanRevision.revision.desc()).first())
            revision = (latest[0] if latest else 0) + 1
        else:
            plan_key, revision = uuid.uuid4().hex, 1
        row = DirectionalPlanRevision(
            well_id=well_id, wellbore_id=wellbore_id, plan_key=plan_key, name=str(name).strip(),
            revision=revision, parent_id=parent_id, status="draft", method=result.method or METHOD,
            method_version=result.version or PLAN_VERSION, inputs=json.loads(json.dumps(inputs)),
            results=_results(result), note=note, created_by=user_id,
        )
        session.add(row)
        session.flush()
        return _dto(row)


def revise_plan(db, revision_id: int, inputs: Dict[str, Any], *, note: str = "",
                user_id: Optional[int] = None) -> Dict[str, Any]:
    """New revision of the same plan derived from ``revision_id``; the old one is untouched."""
    parent = get_plan(db, revision_id)
    return save_plan(db, well_id=parent["well_id"], wellbore_id=parent["wellbore_id"], name=parent["name"],
                     inputs=inputs, plan_key=parent["plan_key"], parent_id=parent["id"], note=note, user_id=user_id)


def clone_plan(db, revision_id: int, name: str, *, user_id: Optional[int] = None) -> Dict[str, Any]:
    """A new plan (new key, revision 1) starting from an existing revision's inputs."""
    source = get_plan(db, revision_id)
    return save_plan(db, well_id=source["well_id"], wellbore_id=source["wellbore_id"], name=name,
                     inputs=source["inputs"], parent_id=source["id"],
                     note=f"Cloned from {source['name']} rev {source['revision']}", user_id=user_id)


def set_status(db, revision_id: int, status: str) -> Dict[str, Any]:
    from core.database import DirectionalPlanRevision

    if status not in STATUSES:
        raise ValueError(f"Unknown plan status {status!r}; use one of {', '.join(STATUSES)}.")
    with db.session_scope() as session:
        row = session.get(DirectionalPlanRevision, revision_id)
        if row is None:
            raise LookupError(f"Plan revision {revision_id} does not exist.")
        if row.status == "archived" and status != "archived":
            raise ValueError("An archived revision stays archived; revise or clone it instead.")
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
