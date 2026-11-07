"""M132: revision-aware 3D layers (W6 Trajectory › 3D view).

The 3D view draws stored, immutable records only - a base survey revision, an optional second survey revision,
a directional plan revision with its targets and a well architecture revision - in ONE local frame: north / east
/ TVD relative to the base survey revision's first station, in its declared azimuth reference and depth datum.
Nothing is transformed: there is no CRS, grid-convergence, declination or datum conversion here. A layer is
overlaid only when the stored records prove it is in the same frame; otherwise it is listed as NOT DRAWN with
the reason:

* base survey revision - must pass ``survey_revisions.verify_for_use`` (station hash, results hash, results
  recomputation); a failing revision draws nothing.
* second survey revision - same declared azimuth reference and depth datum, and the same first station (MD,
  north, east, TVD): two revisions with different first stations have different origins.
* plan revision - its tie-in pins the base revision (``survey_revision_id`` and the stations SHA-256, checked at
  save by ``directional_plans``), both declare the same references, and the stored results pass their SHA-256.
  Without a base survey a plan is drawn in its own tie-in frame (labelled so) and nothing else is overlaid.
* targets - the plan's stored targets, drawn only with the plan; a target missing a coordinate is not placed.
* architecture revision - only when it is pinned to the base survey revision (``survey_revision_id``: the
  survey it was drawn against). Strings are drawn along the base path and shoes as markers, positions by the
  canonical minimum-curvature arc (``trajectory_compare.WellPath``); anything below the last survey station is
  not drawn (no extrapolation).

Scope: records of another well are refused; with an explicitly selected wellbore, records of another wellbore
and records without a wellbore are excluded and listed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

LAYER_METHOD = "M132 revision-aware 3D layers v1"
LAYER_LABEL = ("DISPLAY ONLY — LOCAL NORTH / EAST / TVD OF THE BASE RECORD — NO CRS, DECLINATION, CONVERGENCE OR "
               "DATUM TRANSFORMATION")
SURVEY, COMPARE, PLAN, TARGETS, ARCHITECTURE = "survey", "compare", "plan", "targets", "architecture"
LAYER_KEYS = (SURVEY, COMPARE, PLAN, TARGETS, ARCHITECTURE)
DRAWN, NOT_DRAWN, NOT_SELECTED = "DRAWN", "NOT DRAWN", "NOT SELECTED"
REFERENCE_KEYS = ("azimuth_reference", "depth_datum")
ORIGIN_TOLERANCE_M = 1e-6          # same first station: stored values are equal (float round-trip only)


@dataclass(frozen=True)
class Marker:
    name: str
    east: float
    north: float
    tvd: float
    md: Optional[float]
    note: str = ""


@dataclass(frozen=True)
class Polyline:
    name: str
    east: tuple
    north: tuple
    tvd: tuple


@dataclass(frozen=True)
class Layer:
    key: str
    label: str
    status: str
    reason: str = ""
    source: str = ""
    path: Optional[Polyline] = None
    markers: tuple = ()
    intervals: tuple = ()
    not_placed: tuple = ()             # (name, reason)

    @property
    def drawn(self) -> bool:
        return self.status == DRAWN


@dataclass
class LayerSet:
    unit: str
    scope_label: str
    frame_label: str
    layers: List[Layer]
    method: str = LAYER_METHOD
    label: str = LAYER_LABEL
    excluded: List[Tuple[str, str]] = field(default_factory=list)

    def layer(self, key: str) -> Layer:
        return next(layer for layer in self.layers if layer.key == key)

    @property
    def drawable(self) -> bool:
        return any(layer.drawn and layer.path is not None for layer in self.layers)


# -- helpers -----------------------------------------------------------------------------------------------------
def _display(value: Optional[float], unit: str) -> Optional[float]:
    from core.well_trajectory import to_display_units

    return to_display_units(value, unit)


def _refs(record: Optional[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    record = record or {}
    source = record.get("references") if "references" in record else record
    return {key: (str((source or {}).get(key) or "").strip() or None) for key in REFERENCE_KEYS}


def references_match(a: Dict[str, Optional[str]], b: Dict[str, Optional[str]], a_label: str,
                     b_label: str) -> Tuple[bool, str]:
    """Both sides declare both references and they are equal (case-insensitive); otherwise the reason."""
    for key in REFERENCE_KEYS:
        name = key.replace("_", " ")
        if not a.get(key):
            return False, f"{a_label} {name} NOT DECLARED (compatibility unknown; nothing is assumed)"
        if not b.get(key):
            return False, f"{b_label} {name} NOT DECLARED (compatibility unknown; nothing is assumed)"
        if a[key].lower() != b[key].lower():
            return False, f"{name} differs: {a_label} {a[key]} vs {b_label} {b[key]} (no transformation is applied)"
    return True, ""


def _ref_text(refs: Dict[str, Optional[str]]) -> str:
    return f"{refs.get('azimuth_reference') or 'azimuth reference NOT DECLARED'} north, " \
           f"datum {refs.get('depth_datum') or 'NOT DECLARED'}"


def _polyline(name: str, rows: Sequence[Dict[str, Any]], unit: str) -> Optional[Polyline]:
    points = [(r.get("east"), r.get("north"), r.get("tvd")) for r in rows]
    if len(points) < 2 or any(v is None for p in points for v in p):
        return None
    return Polyline(name, tuple(_display(p[0], unit) for p in points), tuple(_display(p[1], unit) for p in points),
                    tuple(_display(p[2], unit) for p in points))


def _well_path(revision: Dict[str, Any]):
    from core.trajectory_compare import Station, WellPath

    return WellPath(name=f"survey revision {revision.get('revision')}", stations=tuple(
        Station(float(s["md"]), float(s["inc"]), float(s["azi"]), float(s["north"]), float(s["east"]),
                float(s["tvd"])) for s in revision["results"]))


def _scope_problem(record: Dict[str, Any], what: str, well_id: Optional[int],
                   wellbore_id: Optional[int]) -> Optional[str]:
    if well_id is not None and record.get("well_id") != well_id:
        return f"{what} belongs to another well"
    if wellbore_id:
        bore = record.get("wellbore_id")
        if bore is None:
            return f"{what} is not recorded for a wellbore (excluded from a wellbore view)"
        if bore != wellbore_id:
            return f"{what} is recorded for wellbore #{bore}, not the selected wellbore #{wellbore_id}"
    return None


def survey_label(revision: Dict[str, Any]) -> str:
    return f"Survey revision {revision.get('revision')} ({_ref_text(_refs(revision))})"


def plan_label(plan: Dict[str, Any]) -> str:
    return f"Plan '{plan.get('name')}' revision {plan.get('revision')} [{plan.get('status')}]"


def architecture_label(architecture: Dict[str, Any]) -> str:
    return f"Architecture revision {architecture.get('revision')}"


# -- assembly (pure) ---------------------------------------------------------------------------------------------
def assemble(survey: Optional[Dict[str, Any]] = None, *, compare: Optional[Dict[str, Any]] = None,
             plan: Optional[Dict[str, Any]] = None, architecture: Optional[Dict[str, Any]] = None,
             unit: str = "m", well_id: Optional[int] = None, wellbore_id: Optional[int] = None,
             scope_label: str = "") -> LayerSet:
    """Layers from stored record dicts (``survey_revisions.get_revision``, ``directional_plans.get_plan``,
    ``well_architecture.get_revision``)."""
    from core import survey_revisions as sr

    layers: Dict[str, Layer] = {}
    base_ok = False
    frame = "Nothing drawn: select a survey revision or a plan revision."
    if survey is not None:
        source = f"survey_revisions #{survey.get('id')} (stations SHA-256 {str(survey.get('stations_sha256'))[:12]}…)"
        problem = _scope_problem(survey, "the survey revision", well_id, wellbore_id)
        if problem is None:
            try:
                sr.verify_for_use(survey, "the 3D view")
            except sr.SurveyRevisionError as exc:
                problem = str(exc)
        path = None if problem else _polyline(survey_label(survey), survey.get("results") or [], unit)
        if problem is None and path is None:
            problem = "fewer than two computed stations"
        if problem:
            layers[SURVEY] = Layer(SURVEY, survey_label(survey), NOT_DRAWN, problem, source)
        else:
            base_ok = True
            first = survey["results"][0]
            frame = (f"Frame: survey revision {survey.get('revision')} — north / east / TVD relative to its first "
                     f"station (MD {first['md']:g} m); {_ref_text(_refs(survey))}")
            layers[SURVEY] = Layer(SURVEY, survey_label(survey), DRAWN, "integrity VERIFIED", source, path)
    else:
        layers[SURVEY] = Layer(SURVEY, "Survey revision", NOT_SELECTED, "no survey revision selected")
    base_failed = survey is not None and not base_ok
    layers[COMPARE] = _compare_layer(survey if base_ok else None, compare, unit, well_id, wellbore_id, base_failed)
    plan_layer, targets_layer, plan_frame = _plan_layers(survey if base_ok else None, plan, unit, well_id,
                                                         wellbore_id, base_failed)
    layers[PLAN], layers[TARGETS] = plan_layer, targets_layer
    if survey is None and plan_layer.drawn:
        frame = plan_frame
    layers[ARCHITECTURE] = _architecture_layer(survey if base_ok else None, architecture, unit, well_id,
                                               wellbore_id, base_failed)
    return LayerSet(unit, scope_label, frame, [layers[key] for key in LAYER_KEYS])


def _compare_layer(base, compare, unit, well_id, wellbore_id, base_failed) -> Layer:
    if compare is None:
        return Layer(COMPARE, "Second survey revision", NOT_SELECTED, "no second survey revision selected")
    from core import survey_revisions as sr

    label = survey_label(compare) + " — second"
    source = f"survey_revisions #{compare.get('id')}"
    if base is None:
        return Layer(COMPARE, label, NOT_DRAWN, "the base survey revision failed its checks" if base_failed
                     else "select a base survey revision first (the second revision is overlaid on it)", source)
    if compare.get("id") == base.get("id"):
        return Layer(COMPARE, label, NOT_DRAWN, "the same revision as the base", source)
    problem = _scope_problem(compare, "the second survey revision", well_id, wellbore_id)
    if problem is None:
        try:
            sr.verify_for_use(compare, "the 3D view")
        except sr.SurveyRevisionError as exc:
            problem = str(exc)
    if problem is None:
        ok, why = references_match(_refs(base), _refs(compare), "base", "second revision")
        problem = None if ok else why
    if problem is None:
        a, b = base["results"][0], compare["results"][0]
        if any(abs(float(a[k]) - float(b[k])) > ORIGIN_TOLERANCE_M for k in ("md", "north", "east", "tvd")):
            problem = (f"first station differs (MD {a['md']:g} vs {b['md']:g} m): the two revisions have different "
                       "origins; not overlaid")
    path = None if problem else _polyline(label, compare.get("results") or [], unit)
    if problem is None and path is None:
        problem = "fewer than two computed stations"
    if problem:
        return Layer(COMPARE, label, NOT_DRAWN, problem, source)
    return Layer(COMPARE, label, DRAWN, "same references and first station as the base; integrity VERIFIED",
                 source, path)


def _plan_layers(base, plan, unit, well_id, wellbore_id, base_failed):
    from core.directional_plans import result_fingerprint

    if plan is None:
        return (Layer(PLAN, "Plan revision", NOT_SELECTED, "no plan revision selected"),
                Layer(TARGETS, "Targets", NOT_SELECTED, "no plan revision selected"), "")
    label = plan_label(plan)
    source = f"directional_plan_revisions #{plan.get('id')}"
    inputs, results = plan.get("inputs") or {}, plan.get("results") or {}
    tie_in = inputs.get("tie_in") or {}
    problem = _scope_problem(plan, "the plan revision", well_id, wellbore_id)
    if problem is None and base_failed:
        problem = "the base survey revision failed its checks"
    recorded = results.get("result_sha256")
    if problem is None and recorded and result_fingerprint(results) != recorded:
        problem = "the stored plan results fail their SHA-256 check"
    plan_refs = _refs(inputs)
    frame = ""
    if problem is None and base is not None:
        pinned = tie_in.get("survey_revision_id")
        if pinned is None:
            problem = ("the plan is not tied in to a survey revision: its positions are relative to its own tie-in, "
                       "not to this survey's origin")
        elif pinned != base.get("id") or tie_in.get("survey_sha256") != base.get("stations_sha256"):
            problem = (f"the plan is tied in to survey revision record #{pinned}, not to the base revision "
                       f"{base.get('revision')}; select that revision as the base")
        else:
            ok, why = references_match(_refs(base), plan_refs, "survey", "plan")
            problem = None if ok else why
    elif problem is None:
        frame = (f"Frame: plan '{plan.get('name')}' revision {plan.get('revision')} — its own tie-in (MD "
                 f"{float(tie_in.get('md', 0.0)):g} m); {_ref_text(plan_refs)}; no survey revision selected")
    path = None if problem else _polyline(label, results.get("stations") or [], unit)
    if problem is None and path is None:
        problem = "the plan has fewer than two stored stations"
    sha_note = "results SHA-256 verified" if recorded else "results SHA-256 NOT RECORDED (saved before it existed)"
    if problem:
        return (Layer(PLAN, label, NOT_DRAWN, problem, source),
                Layer(TARGETS, "Targets of " + label, NOT_DRAWN, "drawn only with their plan", source), "")
    reason = (f"tied in to survey revision {base.get('revision')} at MD {float(tie_in['md']):g} m; same references; "
              if base is not None else "own tie-in frame; ") + sha_note
    plan_layer = Layer(PLAN, label, DRAWN, reason, source, path)
    markers, not_placed = [], []
    for i, target in enumerate(inputs.get("targets") or [], start=1):
        name = str(target.get("name") or f"target {i}")
        values = [target.get(k) for k in ("east", "north", "tvd")]
        if any(v is None or not math.isfinite(float(v)) for v in values):
            not_placed.append((name, "a coordinate is not recorded"))
            continue
        radius = target.get("radius")
        note = f"radius {_display(float(radius), unit):g} {unit}" if radius not in (None, "") else "radius not recorded"
        markers.append(Marker(name, *(_display(float(v), unit) for v in values), None, note))
    if markers or not_placed:
        targets_layer = Layer(TARGETS, "Targets of " + label, DRAWN if markers else NOT_DRAWN,
                              "in the plan's frame" if markers else "no target has all coordinates", source,
                              markers=tuple(markers), not_placed=tuple(not_placed))
    else:
        targets_layer = Layer(TARGETS, "Targets of " + label, NOT_DRAWN, "the plan stores no targets", source)
    return plan_layer, targets_layer, frame


def _architecture_layer(base, architecture, unit, well_id, wellbore_id, base_failed) -> Layer:
    from core.well_architecture import POINT_KINDS, STRINGS

    if architecture is None:
        return Layer(ARCHITECTURE, "Architecture revision", NOT_SELECTED, "no architecture revision selected")
    label = architecture_label(architecture)
    source = f"well_architecture_revisions #{architecture.get('id')}"
    problem = _scope_problem(architecture, "the architecture revision", well_id, wellbore_id)
    if problem is None and base is None:
        problem = ("the base survey revision failed its checks" if base_failed else
                   "architecture depths are placed on a survey revision only; select the survey it was drawn against")
    if problem is None:
        pinned = architecture.get("survey_revision_id")
        if pinned is None:
            problem = ("the architecture revision is not pinned to a survey revision; its MDs are not placed on "
                       f"survey revision {base.get('revision')}")
        elif pinned != base.get("id"):
            problem = (f"the architecture revision was drawn against survey revision record #{pinned}, not the base "
                       f"revision {base.get('revision')}")
    if problem:
        return Layer(ARCHITECTURE, label, NOT_DRAWN, problem, source)
    path = _well_path(base)
    first, last = path.md_range
    intervals, markers, not_placed = [], [], []

    def place(md):
        position = path.position(float(md))
        return None if position is None else tuple(_display(v, unit) for v in (position[1], position[0], position[2]))

    for item in architecture.get("components") or []:
        kind, name = item.get("kind"), item.get("name") or item.get("kind")
        top, bottom = item.get("top_md"), item.get("bottom_md")
        if kind in STRINGS:
            if top is None or bottom is None:
                not_placed.append((f"{kind} {name}", "top or bottom MD not recorded"))
                continue
            lo, hi = max(float(top), first), min(float(bottom), last)
            if lo >= hi:
                not_placed.append((f"{kind} {name}", f"outside the surveyed MD range {first:g}–{last:g} m"))
                continue
            mds = [lo] + [s.md for s in path.stations if lo < s.md < hi] + [hi]
            points = [place(md) for md in mds]
            intervals.append(Polyline(f"{kind} {name}", tuple(p[0] for p in points), tuple(p[1] for p in points),
                                      tuple(p[2] for p in points)))
            if float(bottom) > last:
                not_placed.append((f"{kind} {name}", f"below the last survey station from {last:g} m (not drawn; "
                                                     "no extrapolation)"))
        elif kind in POINT_KINDS:
            if top is None:
                not_placed.append((f"{kind} {name}", "MD not recorded"))
                continue
            point = place(top)
            if point is None:
                not_placed.append((f"{kind} {name}", f"MD {float(top):g} m outside the surveyed range "
                                                     f"{first:g}–{last:g} m (no extrapolation)"))
                continue
            markers.append(Marker(f"{kind} {name}", *point, _display(float(top), unit), "minimum-curvature position"))
    status = DRAWN if (intervals or markers) else NOT_DRAWN
    reason = (f"pinned to survey revision {base.get('revision')}; positions on its minimum-curvature path"
              if status == DRAWN else "no string or point component lies within the surveyed MD range")
    return Layer(ARCHITECTURE, label, status, reason, source, markers=tuple(markers), intervals=tuple(intervals),
                 not_placed=tuple(not_placed))


# -- database ----------------------------------------------------------------------------------------------------
def catalogue(db, well_id: Optional[int], wellbore_id: Optional[int] = None) -> Dict[str, Any]:
    """Selectable records of the scope as plain dicts, plus the excluded ones with the reason."""
    from core import directional_plans as dp
    from core import survey_revisions as sr
    from core import well_architecture as wa

    out: Dict[str, Any] = {"surveys": [], "plans": [], "architectures": [], "excluded": []}
    if not well_id:
        return out
    groups = (("surveys", sr.list_revisions(db, well_id), survey_label, "survey_revisions"),
              ("plans", dp.list_plans(db, well_id), plan_label, "directional_plan_revisions"),
              ("architectures", wa.list_revisions(db, well_id), architecture_label, "well_architecture_revisions"))
    for key, records, labeller, table in groups:
        for record in records:
            problem = _scope_problem(record, labeller(record), well_id, wellbore_id)
            if problem:
                out["excluded"].append((f"{table} #{record.get('id')}", problem))
            else:
                out[key].append({"id": record["id"], "label": labeller(record), "wellbore_id": record.get("wellbore_id")})
    return out


def build(db, well_id: int, *, wellbore_id: Optional[int] = None, survey_id: Optional[int] = None,
          compare_id: Optional[int] = None, plan_id: Optional[int] = None, architecture_id: Optional[int] = None,
          unit: str = "m") -> LayerSet:
    from core import directional_plans as dp
    from core import survey_revisions as sr
    from core import well_architecture as wa

    survey = sr.get_revision(db, survey_id) if survey_id else None
    compare = sr.get_revision(db, compare_id) if compare_id else None
    plan = dp.get_plan(db, plan_id) if plan_id else None
    architecture = wa.get_revision(db, architecture_id) if architecture_id else None
    scope = f"Well #{well_id}" + (f", wellbore #{wellbore_id} only" if wellbore_id else ", whole well")
    result = assemble(survey, compare=compare, plan=plan, architecture=architecture, unit=unit, well_id=well_id,
                      wellbore_id=wellbore_id, scope_label=scope)
    result.excluded = list(catalogue(db, well_id, wellbore_id)["excluded"])
    return result


def all_points(layer_set: LayerSet) -> List[Tuple[float, float, float]]:
    """(east, north, tvd) of everything drawn - paths, intervals and markers."""
    points: List[Tuple[float, float, float]] = []
    for layer in layer_set.layers:
        if not layer.drawn:
            continue
        for line in ([layer.path] if layer.path is not None else []) + list(layer.intervals):
            points.extend(zip(line.east, line.north, line.tvd))
        points.extend((m.east, m.north, m.tvd) for m in layer.markers)
    return points


def layer_limits(layer_set: LayerSet, equal: bool = True, margin: float = 0.05):
    """((xmin, xmax), (ymin, ymax), (zmin, zmax)) over every drawn item; the same rule as
    ``trajectory_3d.axis_limits`` (one common span by default, so angles are not distorted)."""
    points = all_points(layer_set)
    if not points:
        raise ValueError("nothing is drawn")
    columns = list(zip(*points))
    spans = [max(c) - min(c) for c in columns]
    centres = [(max(c) + min(c)) / 2.0 for c in columns]
    if equal:
        half = max(max(spans) / 2.0, 0.5) * (1.0 + margin)
        return tuple((centre - half, centre + half) for centre in centres)
    return tuple((centre - max(span / 2.0, 0.5) * (1.0 + margin), centre + max(span / 2.0, 0.5) * (1.0 + margin))
                 for centre, span in zip(centres, spans))
