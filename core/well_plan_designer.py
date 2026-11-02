"""M55: directional well plan design (KOP / build / hold / drop / turn / targets).

Positions are computed ONLY by the canonical minimum-curvature engine
(``core.engineering.engines.trajectory.TrajectoryCalculator``); this module
generates the plan stations. A curve segment is a constant-curvature arc from
the current direction to a target inclination/azimuth at a stated DLS; its
stations are interpolated on the unit sphere (slerp), which is exactly the arc
the minimum-curvature method assumes between stations.

Segments (MD in metres, angles in degrees, DLS in deg/30 m):
* ``{"type": "hold", "length": L}``             – keep direction for L m (a hold
  from surface is the vertical section to the KOP)
* ``{"type": "curve", "inc": I, "azi": A, "dls": D}`` – build/drop/turn to (I, A)
* ``{"type": "hold_to_tvd", "tvd": T}``         – hold until TVD T (inc < 90)

Targets ``{"name", "north", "east", "tvd", "radius"}`` are evaluated (M62)
against the continuous minimum-curvature path between stations, not only the
stations; the closest station is reported alongside. A target without a radius
is never a hit. A segment above the DLS limit is reported, never silently
clipped. Non-finite inputs and antiparallel curves (undefined arc plane) are
explicit errors. Planning aid only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

PLAN_VERSION = "M72 plan designer v3"
ANTIPARALLEL_TOL_DEG = 1e-6
METHOD = "Minimum curvature (canonical TrajectoryCalculator); constant-curvature arcs"


@dataclass
class PlanResult:
    stations: List[Dict[str, float]] = field(default_factory=list)
    segments: List[Dict[str, Any]] = field(default_factory=list)
    targets: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None
    method: str = METHOD
    version: str = PLAN_VERSION

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.stations)


def _vector(inc: float, azi: float) -> tuple:
    i, a = math.radians(inc), math.radians(azi)
    return (math.sin(i) * math.cos(a), math.sin(i) * math.sin(a), math.cos(i))


def _angles(v: Sequence[float]) -> tuple:
    n, e, d = v
    norm = math.sqrt(n * n + e * e + d * d)
    n, e, d = n / norm, e / norm, d / norm
    inc = math.degrees(math.acos(max(-1.0, min(1.0, d))))
    azi = math.degrees(math.atan2(e, n)) % 360.0 if math.hypot(n, e) > 1e-12 else 0.0
    return inc, azi


def dogleg_deg(inc1: float, azi1: float, inc2: float, azi2: float) -> float:
    v1, v2 = _vector(inc1, azi1), _vector(inc2, azi2)
    dot = max(-1.0, min(1.0, sum(a * b for a, b in zip(v1, v2))))
    return math.degrees(math.acos(dot))


def _slerp(v1, v2, t: float):
    dot = max(-1.0, min(1.0, sum(a * b for a, b in zip(v1, v2))))
    omega = math.acos(dot)
    if omega < 1e-12:
        return v1
    s = math.sin(omega)
    return tuple((math.sin((1 - t) * omega) * a + math.sin(t * omega) * b) / s for a, b in zip(v1, v2))


def design_plan(segments: Sequence[Dict[str, Any]], *, step: float = 30.0, dls_limit: Optional[float] = None,
                vs_azimuth: float = 0.0, targets: Sequence[Dict[str, Any]] = (),
                tie_in: Optional[Dict[str, float]] = None) -> PlanResult:
    from core.engineering.engines.trajectory import TrajectoryCalculator

    result = PlanResult()
    problem = _non_finite(segments, targets, tie_in, step, dls_limit, vs_azimuth)
    if problem:
        result.error = problem
        return result
    if step <= 0:
        result.error = "Station step must be positive."
        return result
    md = float((tie_in or {}).get("md", 0.0))
    inc = float((tie_in or {}).get("inc", 0.0))
    azi = float((tie_in or {}).get("azi", 0.0))
    raw = [{"md": md, "inc": inc, "azi": azi}]

    def add(md_value, inc_value, azi_value):
        if md_value - raw[-1]["md"] > 1e-9:
            raw.append({"md": md_value, "inc": inc_value, "azi": azi_value})

    for number, segment in enumerate(segments, 1):
        kind = str(segment.get("type", "")).lower()
        start_md = md
        if kind == "hold":
            length = float(segment.get("length", 0))
            if length <= 0:
                result.error = f"Segment {number}: hold length must be positive."
                return result
            n = max(1, math.ceil(length / step))
            for k in range(1, n + 1):
                add(md + length * k / n, inc, azi)
            md += length
            label = "Vertical to KOP" if inc == 0 and number == 1 else "Hold"
            result.segments.append({"number": number, "type": label, "start_md": start_md, "end_md": md,
                                    "length": length, "dls": 0.0, "inc": inc, "azi": azi})
        elif kind == "curve":
            target_inc, target_azi = float(segment["inc"]), float(segment.get("azi", azi)) % 360.0
            dls = float(segment.get("dls", 0))
            if not 0 <= target_inc <= 180:
                result.error = f"Segment {number}: inclination must be between 0 and 180 degrees."
                return result
            if dls <= 0:
                result.error = f"Segment {number}: DLS must be positive."
                return result
            dogleg = dogleg_deg(inc, azi, target_inc, target_azi)
            if dogleg < 1e-9:
                result.warnings.append(f"Segment {number}: already at the target direction; no curve added.")
                continue
            if dogleg > 180.0 - ANTIPARALLEL_TOL_DEG:
                result.error = (
                    f"Segment {number}: the target direction is antiparallel to the current one "
                    f"(dogleg {dogleg:.4f} deg); the curve plane is undefined. Split it into two curves."
                )
                return result
            length = dogleg / dls * 30.0
            v1, v2 = _vector(inc, azi), _vector(target_inc, target_azi)
            n = max(1, math.ceil(length / step))
            for k in range(1, n + 1):
                i_k, a_k = _angles(_slerp(v1, v2, k / n))
                add(md + length * k / n, i_k, a_k if k < n or target_inc > 0 else 0.0)
            kind_label = ("Build" if target_inc > inc + 1e-9 else "Drop" if target_inc < inc - 1e-9 else "Turn")
            if abs(((target_azi - azi + 180) % 360) - 180) > 1e-9 and kind_label != "Turn" and inc > 0:
                kind_label += " & turn"
            result.segments.append({"number": number, "type": kind_label, "start_md": start_md, "end_md": md + length,
                                    "length": length, "dls": dls, "inc": target_inc, "azi": target_azi})
            if dls_limit is not None and dls > dls_limit + 1e-9:
                result.warnings.append(
                    f"Segment {number} ({kind_label}) DLS {dls:.2f} deg/30 m exceeds the limit {dls_limit:.2f} deg/30 m."
                )
            md += length
            inc, azi = target_inc, target_azi
        elif kind == "hold_to_tvd":
            # TVD at the current MD comes from the canonical engine, not an estimate.
            current = _shift_to_tie_in(TrajectoryCalculator.calculate([dict(s) for s in raw], vs_azimuth=vs_azimuth),
                                       tie_in, vs_azimuth)[-1]["tvd"]
            target_tvd = float(segment["tvd"])
            if inc >= 90 - 1e-9:
                result.error = f"Segment {number}: cannot hold to a TVD at {inc:.1f} deg inclination."
                return result
            if target_tvd <= current:
                result.error = f"Segment {number}: target TVD {target_tvd:.1f} m is not below the current {current:.1f} m."
                return result
            length = (target_tvd - current) / math.cos(math.radians(inc))
            n = max(1, math.ceil(length / step))
            for k in range(1, n + 1):
                add(md + length * k / n, inc, azi)
            result.segments.append({"number": number, "type": "Hold to TVD", "start_md": start_md,
                                    "end_md": md + length, "length": length, "dls": 0.0, "inc": inc, "azi": azi})
            md += length
        else:
            result.error = f"Segment {number}: unknown type '{segment.get('type')}'."
            return result

    if len(raw) < 2:
        result.error = "The plan has no segments."
        return result
    result.stations = _shift_to_tie_in(TrajectoryCalculator.calculate(raw, vs_azimuth=vs_azimuth), tie_in, vs_azimuth)
    for target in targets:
        result.targets.append(evaluate_target(result.stations, target))
    return result


def _shift_to_tie_in(stations, tie_in, vs_azimuth):
    """M72: a tie-in with a position (survey station) moves the whole path there.

    Without ``tvd``, ``north`` and ``east`` the canonical engine's own origin is
    kept (unchanged from v2). VS is the projection on the VS azimuth and HD the
    closure distance, both recomputed from the shifted coordinates.
    """
    tie_in = tie_in or {}
    if not stations or not all(k in tie_in for k in ("tvd", "north", "east")):
        return stations
    d_tvd = float(tie_in["tvd"]) - stations[0]["tvd"]
    d_n, d_e = float(tie_in["north"]) - stations[0]["north"], float(tie_in["east"]) - stations[0]["east"]
    angle = math.radians(float(vs_azimuth or 0.0))
    out = []
    for station in stations:
        row = dict(station)
        row["tvd"] += d_tvd
        row["north"] += d_n
        row["east"] += d_e
        row["vs"] = row["north"] * math.cos(angle) + row["east"] * math.sin(angle)
        row["hd"] = math.hypot(row["north"], row["east"])
        out.append(row)
    return out


SOLVER_VERSION = "M72 build-hold target solver v1"


def solve_build_hold(target: Dict[str, float], *, kop_md: float, dls: float,
                     tie_in: Optional[Dict[str, float]] = None, max_inc: float = 90.0) -> Dict[str, Any]:
    """Closed-form J-profile (vertical hold - build - tangent hold) through a target centre.

    Objective: pass exactly through the target centre (TVD, N, E). Constraints:
    a vertical tie-in (inclination 0) at or above the KOP, a constant build rate
    ``dls`` (deg/30 m) and a hold inclination <= ``max_inc``. In the vertical
    plane of the target azimuth with horizontal offset H and depth V below the
    KOP, the build radius is R = 5400/(pi*dls) and the hold angle is
    theta = atan2(V, R - H) - acos(R/d), d = sqrt((R - H)^2 + V^2); the
    tangent length is sqrt(d^2 - R^2). The target is infeasible when it lies
    inside the build circle (d < R), above the KOP, or needs theta > max_inc.
    No iteration: the answer is deterministic. Returns ``{"feasible": bool,
    "reason", "segments", "inc", "azi", "hold_length", ...}``.
    """
    tie_in = dict(tie_in or {})
    out: Dict[str, Any] = {"feasible": False, "method": SOLVER_VERSION, "segments": []}
    values = [kop_md, dls, max_inc] + [target.get(k) for k in ("tvd", "north", "east")]
    if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in values):
        out["reason"] = "Target TVD/N/E, KOP, build rate and max inclination must be finite numbers."
        return out
    if abs(float(tie_in.get("inc", 0.0))) > 1e-9:
        out["reason"] = "Only a vertical tie-in is supported by this solver (3D tie-in solving is not implemented)."
        return out
    tie_md = float(tie_in.get("md", 0.0))
    tie_tvd = float(tie_in.get("tvd", tie_md))
    tie_n, tie_e = float(tie_in.get("north", 0.0)), float(tie_in.get("east", 0.0))
    if dls <= 0:
        out["reason"] = "The build rate must be positive."
        return out
    if kop_md < tie_md:
        out["reason"] = f"The KOP {kop_md:g} m is above the tie-in MD {tie_md:g} m."
        return out
    kop_tvd = tie_tvd + (kop_md - tie_md)
    dn, de = float(target["north"]) - tie_n, float(target["east"]) - tie_e
    h, v = math.hypot(dn, de), float(target["tvd"]) - kop_tvd
    if v <= 0:
        out["reason"] = "The target is not below the KOP."
        return out
    radius = 5400.0 / (math.pi * dls)
    d = math.hypot(radius - h, v)
    if d < radius:
        out["reason"] = (f"Infeasible: the target lies inside the build circle (radius {radius:.1f} m); "
                         "raise the build rate or move the KOP up.")
        return out
    theta = math.degrees(math.atan2(v, radius - h) - math.acos(radius / d))
    if h <= 1e-9:
        theta = 0.0
    if theta > max_inc + 1e-9:
        out["reason"] = f"Infeasible: the hold inclination {theta:.2f} deg exceeds the limit {max_inc:g} deg."
        return out
    azi = math.degrees(math.atan2(de, dn)) % 360.0 if h > 1e-9 else 0.0
    hold = math.sqrt(max(d * d - radius * radius, 0.0))
    segments = []
    if kop_md - tie_md > 1e-9:
        segments.append({"type": "hold", "length": kop_md - tie_md})
    if theta > 1e-9:
        segments.append({"type": "curve", "inc": theta, "azi": azi, "dls": float(dls)})
    if hold > 1e-9:
        segments.append({"type": "hold", "length": hold})
    out.update({"feasible": True, "reason": "", "segments": segments, "inc": theta, "azi": azi,
                "hold_length": hold, "build_radius": radius, "kop_tvd": kop_tvd, "horizontal_offset": h})
    return out


def _non_finite(segments, targets, tie_in, step, dls_limit, vs_azimuth) -> Optional[str]:
    """First non-finite numeric input, as an explicit error (never propagated as NaN)."""
    def bad(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and not math.isfinite(value)

    for name, value in (("station step", step), ("DLS limit", dls_limit), ("VS azimuth", vs_azimuth)):
        if bad(value):
            return f"The {name} is not a finite number."
    for key, value in (tie_in or {}).items():
        if bad(value):
            return f"Tie-in {key} is not a finite number."
    for number, segment in enumerate(segments, 1):
        for key, value in segment.items():
            if bad(value):
                return f"Segment {number}: {key} is not a finite number."
    for target in targets:
        for key, value in target.items():
            if bad(value):
                return f"Target {target.get('name', '?')}: {key} is not a finite number."
    return None


def arc_point(s1: Dict[str, float], s2: Dict[str, float], frac: float) -> tuple:
    """(md, north, east, tvd) at ``frac`` of the minimum-curvature arc s1 -> s2.

    Between two survey stations minimum curvature is a circular arc of length
    L and dogleg beta in the plane of the two tangents: p(theta) = p1 +
    R(sin(theta) t1 + (1 - cos(theta)) n) with R = L / beta and n the unit
    normal towards t2. A straight segment (beta ~ 0) is the limit.
    """
    t1, t2 = _vector(s1["inc"], s1["azi"]), _vector(s2["inc"], s2["azi"])
    length = s2["md"] - s1["md"]
    p1 = (s1["north"], s1["east"], s1["tvd"])
    beta = math.acos(max(-1.0, min(1.0, sum(a * b for a, b in zip(t1, t2)))))
    if beta < 1e-9:
        return (s1["md"] + frac * length,) + tuple(p + frac * length * t for p, t in zip(p1, t1))
    radius, theta = length / beta, frac * beta
    normal = tuple((b - math.cos(beta) * a) / math.sin(beta) for a, b in zip(t1, t2))
    return (s1["md"] + frac * length,) + tuple(
        p + radius * (math.sin(theta) * t + (1 - math.cos(theta)) * n) for p, t, n in zip(p1, t1, normal)
    )


def closest_on_path(stations: Sequence[Dict[str, float]], point: Sequence[float]) -> Dict[str, float]:
    """Continuous closest approach of the minimum-curvature path to ``point`` (N, E, TVD).

    Each interval is sampled, then the best bracket is refined by golden
    section to 1e-9 of the interval; the result is not limited to stations.
    """
    best = None
    golden = (math.sqrt(5) - 1) / 2

    def dist(s1, s2, f):
        md, n, e, tvd = arc_point(s1, s2, f)
        return math.dist((n, e, tvd), point), md, (n, e, tvd)

    for s1, s2 in zip(stations, stations[1:]):
        if s2["md"] - s1["md"] <= 0:
            continue
        samples = 32
        values = [dist(s1, s2, k / samples) for k in range(samples + 1)]
        k = min(range(samples + 1), key=lambda i: values[i][0])
        lo, hi = max(0.0, (k - 1) / samples), min(1.0, (k + 1) / samples)
        a, b = hi - golden * (hi - lo), lo + golden * (hi - lo)
        while hi - lo > 1e-9:
            if dist(s1, s2, a)[0] <= dist(s1, s2, b)[0]:
                hi, b = b, a
                a = hi - golden * (hi - lo)
            else:
                lo, a = a, b
                b = lo + golden * (hi - lo)
        candidate = min([values[k], dist(s1, s2, (lo + hi) / 2)], key=lambda v: v[0])
        if best is None or candidate[0] < best[0]:
            best = candidate
    if best is None:
        only = stations[0]
        best = (math.dist((only["north"], only["east"], only["tvd"]), point), only["md"],
                (only["north"], only["east"], only["tvd"]))
    distance, md, (north, east, tvd) = best
    return {"distance": distance, "md": md, "north": north, "east": east, "tvd": tvd}


def evaluate_target(stations: Sequence[Dict[str, float]], target: Dict[str, Any]) -> Dict[str, Any]:
    """Target miss distance on the continuous arc; the closest station is kept for transparency."""
    point = (float(target["north"]), float(target["east"]), float(target["tvd"]))
    near = closest_on_path(stations, point)
    station = min(stations, key=lambda s: math.dist((s["north"], s["east"], s["tvd"]), point))
    radius = float(target.get("radius", 0) or 0)
    return {
        "name": target.get("name", "Target"), "closest_md": near["md"], "distance": near["distance"],
        "closest_point": {"north": near["north"], "east": near["east"], "tvd": near["tvd"]},
        "closest_station_md": station["md"],
        "station_distance": math.dist((station["north"], station["east"], station["tvd"]), point),
        "radius": radius, "hit": radius > 0 and near["distance"] <= radius,
        "method": "continuous minimum-curvature arc (golden-section refined)",
    }
