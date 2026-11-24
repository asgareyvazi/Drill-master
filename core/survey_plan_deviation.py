"""M368: actual survey vs directional plan - centreline deviation per surveyed station, and target status.

SCREENING. For every station of an immutable survey revision below the plan's tie-in, the closest point on the
plan's continuous minimum-curvature path (``core.well_plan_designer.closest_on_path``) is found, and the offset is
decomposed in the plan's local frame at that point:

* ``along``  - along the plan tangent (non-zero only when the closest point is the plan's first or last station);
* ``high``   - towards the high side, perpendicular to the tangent (positive = the survey is HIGH of the plan);
* ``right``  - horizontal, perpendicular to the tangent (positive = the survey is RIGHT of the plan, looking
  down-hole).

Frame: ``down x t`` gives the right vector and ``right x t`` the high-side vector in (north, east, TVD-down).
Where the plan is vertical (inclination below ``VERTICAL_INC_DEG``) high side and right are undefined and are
reported as None with that reason; the 3D distance and the TVD difference are still given.

What it refuses (NOT ASSESSED, nothing computed):

* a survey revision or plan of another well / wellbore, or a stored survey failing its SHA-256 check;
* stored plan results failing their SHA-256 check;
* a plan not tied in to a survey revision, or tied in to a revision whose stored stations no longer match;
* different azimuth reference or depth datum between the survey and the plan (never converted here);
* an actual survey that does not contain the plan's tie-in survey up to the tie-in MD (different origin / frame).

No positional uncertainty, no ellipses, no ISCWSA: a deviation inside a declared tolerance is not a statement that
the well is inside its uncertainty envelope. A tolerance is never defaulted: without one, every row is NOT ASSESSED
against a tolerance and only the geometry is reported. Lengths are metres (the stored unit of both records).
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

METHOD_ID = "m368.survey_plan_deviation"
METHOD_VERSION = "M368 survey-vs-plan centreline deviation v1"
CALCULATOR = "Survey vs plan deviation"
LABEL = ("SCREENING - centreline deviation of the actual survey from the plan; no positional uncertainty, "
         "no ISCWSA, not an anti-collision result")
VERTICAL_INC_DEG = 0.5        # below this the plan has no defined high side / right direction
MD_TOLERANCE_M = 1e-6
POSITION_TOLERANCE_M = 1e-6   # stations of the tie-in survey and of the actual survey are the same within this
ANGLE_TOLERANCE_DEG = 1e-9

COMPUTED, NOT_ASSESSED = "COMPUTED", "NOT ASSESSED"
WITHIN, OUTSIDE, NO_TOLERANCE = "WITHIN", "OUTSIDE", "NOT ASSESSED (no tolerance declared)"
HIT, MISS, NOT_REACHED, NO_RADIUS = "HIT", "MISS", "NOT REACHED", "NOT ASSESSED (no radius recorded)"
BEYOND_END, BEFORE_START = "beyond the plan's last station", "before the plan's first station"


class DeviationError(ValueError):
    """The inputs cannot be compared; the message says why (nothing is computed)."""


class IntegrityError(ValueError):
    """A frozen snapshot fails its SHA-256 check."""


def _finite(value) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def snapshot_sha256(snapshot: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(snapshot).encode("utf-8")).hexdigest()


def _unit(inc: float, azi: float) -> Tuple[float, float, float]:
    i, a = math.radians(inc), math.radians(azi)
    return (math.sin(i) * math.cos(a), math.sin(i) * math.sin(a), math.cos(i))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(a):
    length = math.sqrt(_dot(a, a))
    return None if length < 1e-12 else tuple(x / length for x in a)


def _tangent(s1: Mapping[str, float], s2: Mapping[str, float], frac: float):
    """Unit tangent of the minimum-curvature arc s1 -> s2 at ``frac`` (t = cos(theta) t1 + sin(theta) n)."""
    t1, t2 = _unit(s1["inc"], s1["azi"]), _unit(s2["inc"], s2["azi"])
    beta = math.acos(max(-1.0, min(1.0, _dot(t1, t2))))
    if beta < 1e-9:
        return t1
    normal = tuple((b - math.cos(beta) * a) / math.sin(beta) for a, b in zip(t1, t2))
    theta = frac * beta
    return _norm(tuple(math.cos(theta) * a + math.sin(theta) * n for a, n in zip(t1, normal)))


def _inclination(t) -> float:
    return math.degrees(math.acos(max(-1.0, min(1.0, t[2]))))


def _station(s: Mapping[str, Any]) -> Dict[str, float]:
    out = {}
    for key in ("md", "inc", "azi", "north", "east", "tvd"):
        value = _finite(s.get(key))
        if value is None:
            raise DeviationError(f"a station has no {key}; nothing is assumed")
        out[key] = value
    return out


def _interval(stations: Sequence[Mapping[str, float]], md: float):
    for s1, s2 in zip(stations, stations[1:]):
        if s1["md"] - MD_TOLERANCE_M <= md <= s2["md"] + MD_TOLERANCE_M and s2["md"] > s1["md"]:
            return s1, s2, min(1.0, max(0.0, (md - s1["md"]) / (s2["md"] - s1["md"])))
    return stations[-1], stations[-1], 0.0


def deviation_row(plan: Sequence[Mapping[str, float]], station: Mapping[str, float],
                  tolerance_m: Optional[float]) -> Dict[str, Any]:
    """Offset of one surveyed station from the plan's continuous path, in the plan's local frame."""
    from core.well_plan_designer import closest_on_path

    point = (station["north"], station["east"], station["tvd"])
    near = closest_on_path(plan, point)
    s1, s2, frac = _interval(plan, near["md"])
    tangent = _tangent(s1, s2, frac) if s2 is not s1 else _unit(s1["inc"], s1["azi"])
    offset = (point[0] - near["north"], point[1] - near["east"], point[2] - near["tvd"])
    row: Dict[str, Any] = {
        "md": station["md"], "plan_md": near["md"], "distance_m": near["distance"],
        "tvd_difference_m": point[2] - near["tvd"], "along_m": _dot(offset, tangent),
        "high_m": None, "right_m": None, "frame_note": "", "position_note": "",
    }
    if near["md"] >= plan[-1]["md"] - MD_TOLERANCE_M and row["along_m"] > POSITION_TOLERANCE_M:
        row["position_note"] = BEYOND_END
    elif near["md"] <= plan[0]["md"] + MD_TOLERANCE_M and row["along_m"] < -POSITION_TOLERANCE_M:
        row["position_note"] = BEFORE_START
    if _inclination(tangent) < VERTICAL_INC_DEG:
        row["frame_note"] = (f"plan inclination below {VERTICAL_INC_DEG:g} deg at the closest point: high side and "
                             "right are undefined")
    else:
        right = _norm(_cross((0.0, 0.0, 1.0), tangent))
        high = _norm(_cross(right, tangent))
        row["right_m"], row["high_m"] = _dot(offset, right), _dot(offset, high)
    if tolerance_m is None:
        row["status"] = NO_TOLERANCE
    else:
        row["status"] = WITHIN if near["distance"] <= tolerance_m else OUTSIDE
    return row


def target_row(actual: Sequence[Mapping[str, float]], target: Mapping[str, Any]) -> Dict[str, Any]:
    """Closest approach of the ACTUAL survey path to a plan target centre."""
    from core.well_plan_designer import closest_on_path

    name = str(target.get("name") or "target")
    coords = [_finite(target.get(k)) for k in ("north", "east", "tvd")]
    if any(c is None for c in coords):
        return {"name": name, "status": NOT_ASSESSED, "reason": "a target coordinate is not recorded",
                "distance_m": None, "closest_md": None, "radius_m": None}
    near = closest_on_path(actual, coords)
    radius = _finite(target.get("radius"))
    radius = radius if radius is not None and radius > 0 else None
    out = {"name": name, "distance_m": near["distance"], "closest_md": near["md"], "radius_m": radius}
    if near["md"] >= actual[-1]["md"] - MD_TOLERANCE_M and coords[2] > actual[-1]["tvd"] + POSITION_TOLERANCE_M:
        out.update(status=NOT_REACHED, reason="the closest point is the last surveyed station and the target is "
                                              "deeper; drilling has not reached it")
    elif radius is None:
        out.update(status=NO_RADIUS, reason="the plan records no target radius; no hit/miss is stated")
    else:
        out.update(status=HIT if near["distance"] <= radius else MISS,
                   reason=f"centreline miss {near['distance']:.2f} m vs recorded radius {radius:g} m "
                          "(no positional uncertainty)")
    return out


def evaluate(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    """Pure evaluation of a frozen snapshot (``build_snapshot``); used for display, save and replay."""
    plan = [_station(s) for s in snapshot["plan"]["stations"]]
    actual = [_station(s) for s in snapshot["survey"]["stations"]]
    tolerance = snapshot.get("tolerance_m")
    if len(plan) < 2:
        raise DeviationError("the plan has fewer than two stored stations")
    tie_md = plan[0]["md"]
    below = [s for s in actual if s["md"] >= tie_md - MD_TOLERANCE_M]
    rows = [deviation_row(plan, s, tolerance) for s in below]
    targets = [target_row(actual, t) for t in snapshot["plan"].get("targets") or []] if len(actual) >= 2 else []
    worst = max(rows, key=lambda r: r["distance_m"]) if rows else None
    return {
        "status": COMPUTED, "label": LABEL, "method": METHOD_ID, "method_version": METHOD_VERSION,
        "rows": rows, "targets": targets, "tolerance_m": tolerance,
        "above_tie_in": len(actual) - len(below), "tie_in_md": tie_md,
        "max_distance_m": worst["distance_m"] if worst else None, "max_distance_md": worst["md"] if worst else None,
        "outside": sum(1 for r in rows if r["status"] == OUTSIDE),
        "snapshot_sha256": snapshot_sha256(snapshot),
    }


def _positions(revision: Mapping[str, Any]) -> List[Dict[str, float]]:
    return [_station(s) for s in revision.get("results") or []]


def _same_prefix(pinned: Sequence[Mapping[str, float]], actual: Sequence[Mapping[str, float]],
                 tie_md: float) -> Optional[str]:
    prefix = [s for s in pinned if s["md"] <= tie_md + MD_TOLERANCE_M]
    if len(actual) < len(prefix):
        return "the actual survey has fewer stations than the plan's tie-in survey above the tie-in"
    for a, b in zip(prefix, actual):
        if abs(a["md"] - b["md"]) > MD_TOLERANCE_M or abs(a["inc"] - b["inc"]) > ANGLE_TOLERANCE_DEG \
                or abs(a["azi"] - b["azi"]) > ANGLE_TOLERANCE_DEG \
                or any(abs(a[k] - b[k]) > POSITION_TOLERANCE_M for k in ("north", "east", "tvd")):
            return (f"the actual survey differs from the plan's tie-in survey at MD {a['md']:g} m: the two are not "
                    "in the same frame above the tie-in")
    return None


def build_snapshot(db, survey_id: int, plan_id: int, *, tolerance_m: Optional[float] = None) -> Dict[str, Any]:
    """Read and check the two records; return the frozen inputs, or raise DeviationError with the reason."""
    from core import directional_plans as dp
    from core import survey_revisions as sr

    if tolerance_m is not None:
        tol = _finite(tolerance_m)
        if tol is None or tol <= 0:
            raise DeviationError("the declared tolerance must be a positive number of metres")
        tolerance_m = tol
    survey = sr.get_revision(db, survey_id)
    if survey is None:
        raise DeviationError(f"survey revision record #{survey_id} does not exist")
    if survey["integrity"] != "VERIFIED" or survey.get("results_integrity") == "HASH MISMATCH":
        raise DeviationError("the survey revision fails its SHA-256 check")
    try:
        plan = dp.get_plan(db, int(plan_id))
    except LookupError as exc:
        raise DeviationError(str(exc)) from exc
    inputs, results = plan.get("inputs") or {}, plan.get("results") or {}
    recorded = results.get("result_sha256")
    if recorded and dp.result_fingerprint(results) != recorded:
        raise DeviationError("the stored plan results fail their SHA-256 check")
    if plan["well_id"] != survey["well_id"]:
        raise DeviationError("the plan and the survey revision belong to different wells")
    if plan.get("wellbore_id") and survey.get("wellbore_id") and plan["wellbore_id"] != survey["wellbore_id"]:
        raise DeviationError("the plan and the survey revision belong to different wellbores")
    refs = dp.plan_references(plan)
    if not refs["declared"]:
        raise DeviationError("the plan declares no azimuth reference / depth datum (" + dp.reference_text(plan) + ")")
    for key in ("azimuth_reference", "depth_datum"):
        if str(survey.get(key) or "").strip().lower() != str(refs[key] or "").strip().lower():
            raise DeviationError(f"{key.replace('_', ' ')} differs: survey {survey.get(key) or 'NOT DECLARED'}, "
                                 f"plan {refs[key]} - nothing is converted here")
    tie_in = inputs.get("tie_in") or {}
    pinned_id = tie_in.get("survey_revision_id")
    if pinned_id is None:
        raise DeviationError("the plan is not tied in to a survey revision: its frame is its own tie-in")
    pinned = survey if pinned_id == survey["id"] else sr.get_revision(db, pinned_id)
    if pinned is None or pinned["integrity"] != "VERIFIED" or pinned["stations_sha256"] != tie_in.get("survey_sha256"):
        raise DeviationError("the plan's tie-in survey revision is missing or no longer matches its recorded SHA-256")
    if pinned["well_id"] != survey["well_id"]:
        raise DeviationError("the plan's tie-in survey belongs to another well")
    actual = _positions(survey)
    tie_md = _finite(tie_in.get("md"))
    if tie_md is None:
        raise DeviationError("the plan's tie-in has no MD")
    problem = _same_prefix(_positions(pinned), actual, tie_md)
    if problem:
        raise DeviationError(problem)
    plan_stations = [_station(s) for s in results.get("stations") or []]
    if len(plan_stations) < 2:
        raise DeviationError("the plan has fewer than two stored stations")
    return {
        "survey": {"id": survey["id"], "revision": survey["revision"], "stations_sha256": survey["stations_sha256"],
                   "stations": actual},
        "plan": {"id": plan["id"], "name": plan["name"], "revision": plan["revision"], "result_sha256": recorded,
                 "tie_in_survey_revision_id": pinned_id, "tie_in_md": tie_md, "stations": plan_stations,
                 "targets": list(inputs.get("targets") or [])},
        "references": {"azimuth_reference": refs["azimuth_reference"], "depth_datum": refs["depth_datum"]},
        "unit": "m", "tolerance_m": tolerance_m, "well_id": survey["well_id"],
    }


def run(db, survey_id: int, plan_id: int, *, tolerance_m: Optional[float] = None) -> Dict[str, Any]:
    """Service entry: a NOT ASSESSED result with the reason, or the computed deviation with its snapshot."""
    try:
        snapshot = build_snapshot(db, survey_id, plan_id, tolerance_m=tolerance_m)
        result = evaluate(snapshot)
    except DeviationError as exc:
        return {"status": NOT_ASSESSED, "reason": str(exc), "label": LABEL, "rows": [], "targets": []}
    result["snapshot"] = snapshot
    return result


def _fmt(value, digits=2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def summary_lines(result: Mapping[str, Any]) -> List[str]:
    if result.get("status") != COMPUTED:
        return [f"NOT ASSESSED: {result.get('reason')}", LABEL]
    snap = result.get("snapshot") or {}
    plan, survey = snap.get("plan") or {}, snap.get("survey") or {}
    tol = result["tolerance_m"]
    lines = [LABEL,
             f"Survey revision {survey.get('revision')} vs plan '{plan.get('name')}' revision {plan.get('revision')} "
             f"(tie-in MD {result['tie_in_md']:g} m; {snap.get('references', {}).get('azimuth_reference')} north, "
             f"datum {snap.get('references', {}).get('depth_datum')}); lengths in m.",
             f"{len(result['rows'])} station(s) compared; {result['above_tie_in']} above the tie-in not compared.",
             f"Largest centreline distance {_fmt(result['max_distance_m'])} m at MD {_fmt(result['max_distance_md'], 1)} m.",
             (f"Declared tolerance {tol:g} m: {result['outside']} station(s) OUTSIDE." if tol is not None
              else "No tolerance declared: no station is judged WITHIN or OUTSIDE.")]
    for t in result["targets"]:
        lines.append(f"Target {t['name']}: {t['status']} - {t['reason']}")
    return lines


def case_payload(result: Mapping[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    snap = result["snapshot"]
    inputs = {
        "snapshot": {"value": snap, "unit": "", "label": "frozen survey and plan stations, targets and tolerance",
                     "source": "SNAPSHOT"},
        "snapshot_sha256": {"value": snapshot_sha256(snap), "unit": "", "label": "inputs SHA-256"},
        "survey_revision_id": {"value": snap["survey"]["id"], "unit": "", "label": "survey revision record"},
        "survey_stations_sha256": {"value": snap["survey"]["stations_sha256"], "unit": "",
                                   "label": "survey stations SHA-256"},
        "plan_revision_id": {"value": snap["plan"]["id"], "unit": "", "label": "plan revision record"},
        "tolerance_m": {"value": snap["tolerance_m"], "unit": "m", "label": "declared deviation tolerance",
                        "source": "DECLARED" if snap["tolerance_m"] is not None else "NOT_DECLARED"},
    }
    results: Dict[str, Any] = {
        "status": {"value": result["status"], "label": LABEL},
        "max_distance_m": {"value": result["max_distance_m"], "unit": "m", "label": "largest centreline distance"},
        "outside_count": {"value": result["outside"], "unit": "", "label": "stations outside the tolerance"},
    }
    for i, row in enumerate(result["rows"]):
        tag = f"station_{i:03d}"
        for key in ("md", "plan_md", "distance_m", "high_m", "right_m", "tvd_difference_m"):
            results[f"{tag}_{key}" if key.endswith("_m") else f"{tag}_{key}_m"] = {
                "value": row[key], "unit": "m", "label": key}
        results[f"{tag}_status"] = {"value": row["status"], "label": row["position_note"] or row["frame_note"]}
    for i, t in enumerate(result["targets"]):
        results[f"target_{i:02d}_status"] = {"value": t["status"], "label": f"{t['name']}: {t['reason']}"}
        results[f"target_{i:02d}_distance_m"] = {"value": t["distance_m"], "unit": "m", "label": t["name"]}
    return inputs, results


def unit_of(key: str) -> str:
    return "m" if key.endswith("_m") else ""


def save_case(db, result: Mapping[str, Any], *, well_id: Optional[int], user_id: Optional[int] = None):
    from core import calculation_cases as cc

    if result.get("status") != COMPUTED:
        raise ValueError(f"Nothing to store: the deviation was not computed ({result.get('reason')}).")
    snap = result["snapshot"]
    if well_id is not None and well_id != snap["well_id"]:
        raise ValueError("The deviation belongs to another well than the selected one.")
    inputs, results = case_payload(result)
    return cc.save_case(db, calculator=CALCULATOR,
                        name=f"Survey rev {snap['survey']['revision']} vs plan {snap['plan']['name']} "
                             f"rev {snap['plan']['revision']}",
                        inputs=inputs, results=results, method=METHOD_ID, method_version=METHOD_VERSION,
                        well_id=snap["well_id"], user_id=user_id,
                        note=f"{LABEL}; inputs SHA-256 {inputs['snapshot_sha256']['value']}")


def replay_results(inputs: Mapping[str, Any]) -> Dict[str, Any]:
    snap = inputs["snapshot"]["value"] if isinstance(inputs.get("snapshot"), dict) else None
    if not isinstance(snap, dict):
        raise ValueError("the case holds no frozen deviation snapshot")
    if snapshot_sha256(snap) != (inputs.get("snapshot_sha256") or {}).get("value"):
        raise IntegrityError("the frozen survey/plan snapshot fails its SHA-256 check")
    result = evaluate(snap)
    result["snapshot"] = snap
    return case_payload(result)[1]
