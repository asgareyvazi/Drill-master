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


SOLVER_VERSION = "M86 curve-hold target solver v2"


def _fail(out: Dict[str, Any], code: str, reason: str) -> Dict[str, Any]:
    out.update({"feasible": False, "code": code, "reason": reason, "segments": []})
    return out


def _max_inc_along_arc(t0: Sequence[float], n: Sequence[float], phi: float) -> float:
    """Largest inclination (deg) on the arc t(psi) = cos(psi) t0 + sin(psi) n, psi in [0, phi]."""
    candidates = [0.0, phi]
    base = math.atan2(n[2], t0[2])
    for k in range(-2, 3):
        psi = base + k * math.pi
        if 0.0 < psi < phi:
            candidates.append(psi)
    lowest = min(math.cos(psi) * t0[2] + math.sin(psi) * n[2] for psi in candidates)
    return math.degrees(math.acos(max(-1.0, min(1.0, lowest))))


def solve_build_hold(target: Dict[str, float], *, kop_md: float, dls: float,
                     tie_in: Optional[Dict[str, float]] = None, max_inc: float = 90.0) -> Dict[str, Any]:
    """Closed-form curve-hold profile from any tie-in direction through a target centre.

    The tie-in (MD, inc, azi, TVD, N, E; default: surface, vertical) is held in
    its own direction t0 down to the KOP P0. One constant-curvature arc (radius
    R = 5400/(pi*dls)) then a tangent hold reach the target T. The arc lies in
    the plane of t0 and d = T - P0: with a = d.t0, b = |d - a t0| and the unit
    normal n = (d - a t0)/b, tangency requires a sin(phi) + (R - b) cos(phi) = R,
    so phi = atan2(a, R - b) - acos(R/rho) (mod 360 deg), rho = hypot(a, R - b),
    and the tangent length is sqrt(rho^2 - R^2). For a vertical tie-in this is
    the M72 J-profile formula. Infeasible (structured ``code`` + ``reason``, no
    approximation): target inside the turn circle (rho < R), directly behind the
    tie-in direction, a dogleg >= 180 deg, an inclination above ``max_inc``
    anywhere on the arc, KOP above the tie-in, non-finite inputs. Planning aid.
    """
    tie_in = dict(tie_in or {})
    out: Dict[str, Any] = {"feasible": False, "method": SOLVER_VERSION, "segments": [], "code": ""}
    values = [kop_md, dls, max_inc] + [target.get(k) for k in ("tvd", "north", "east")]
    values += [tie_in.get(k, 0.0) for k in ("md", "inc", "azi", "north", "east")]
    if "tvd" in tie_in:
        values.append(tie_in["tvd"])
    if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in values):
        return _fail(out, "INVALID_INPUT",
                     "Target TVD/N/E, tie-in, KOP, build rate and max inclination must be finite numbers.")
    tie_md, tie_inc, tie_azi = (float(tie_in.get(k, 0.0)) for k in ("md", "inc", "azi"))
    if not 0.0 <= tie_inc <= 180.0:
        return _fail(out, "INVALID_INPUT", f"The tie-in inclination {tie_inc:g} deg is outside 0-180 deg.")
    tie_tvd = float(tie_in.get("tvd", tie_md))
    tie_n, tie_e = float(tie_in.get("north", 0.0)), float(tie_in.get("east", 0.0))
    if dls <= 0:
        return _fail(out, "NON_POSITIVE_RATE", "The build rate must be positive.")
    if kop_md < tie_md:
        return _fail(out, "KOP_ABOVE_TIE_IN", f"The KOP {kop_md:g} m is above the tie-in MD {tie_md:g} m.")
    t0 = _vector(tie_inc, tie_azi)                       # (north, east, down)
    lead = kop_md - tie_md
    p0 = (tie_n + lead * t0[0], tie_e + lead * t0[1], tie_tvd + lead * t0[2])
    d = (float(target["north"]) - p0[0], float(target["east"]) - p0[1], float(target["tvd"]) - p0[2])
    vertical = tie_inc <= 1e-9
    if vertical and d[2] <= 0:
        return _fail(out, "TARGET_NOT_BELOW_KOP", "The target is not below the KOP.")
    if math.sqrt(sum(c * c for c in d)) <= 1e-9:
        return _fail(out, "TARGET_AT_KOP", "The target coincides with the KOP; nothing to solve.")
    radius = 5400.0 / (math.pi * dls)
    a = sum(x * y for x, y in zip(d, t0))
    perp = tuple(x - a * y for x, y in zip(d, t0))
    b = math.sqrt(sum(c * c for c in perp))
    common = {"build_radius": radius, "kop_tvd": p0[2], "kop_north": p0[0], "kop_east": p0[1],
              "horizontal_offset": math.hypot(d[0], d[1]), "along_tie_in": a, "off_tie_in": b}
    out.update(common)
    if b <= 1e-9:
        if a <= 0:
            return _fail(out, "TARGET_BEHIND",
                         "Infeasible: the target lies directly behind the tie-in direction (turn plane undefined).")
        phi, n, hold = 0.0, (0.0, 0.0, 0.0), a
    else:
        n = tuple(c / b for c in perp)
        rho = math.hypot(a, radius - b)
        if rho < radius:
            return _fail(out, "INSIDE_TURN_RADIUS",
                         f"Infeasible: the target lies inside the build circle (radius {radius:.1f} m); "
                         "raise the build rate or move the KOP up.")
        phi = (math.atan2(a, radius - b) - math.acos(radius / rho)) % (2.0 * math.pi)
        if phi > 2.0 * math.pi - 1e-12:
            phi = 0.0
        hold = math.sqrt(max(rho * rho - radius * radius, 0.0))
    dogleg = math.degrees(phi)
    if dogleg >= 180.0 - 1e-9:
        return _fail(out, "TURN_TOO_LARGE",
                     f"Infeasible: the target needs a dogleg of {dogleg:.1f} deg (>= 180 deg) at this build rate.")
    peak = _max_inc_along_arc(t0, n, phi) if phi > 0 else tie_inc
    if peak > max_inc + 1e-9:
        return _fail(out, "INC_LIMIT", f"Infeasible: the hold inclination {peak:.2f} deg exceeds the limit "
                                       f"{max_inc:g} deg.")
    end = tuple(math.cos(phi) * x + math.sin(phi) * y for x, y in zip(t0, n))
    inc, azi = _angles(end)
    if inc <= 1e-9:
        azi = 0.0
    segments = []
    if lead > 1e-9:
        segments.append({"type": "hold", "length": lead})
    if dogleg > 1e-9:
        segments.append({"type": "curve", "inc": inc, "azi": azi, "dls": float(dls)})
    if hold > 1e-9:
        segments.append({"type": "hold", "length": hold})
    out.update({"feasible": True, "code": "OK", "reason": "", "segments": segments, "inc": inc, "azi": azi,
                "hold_length": hold, "dogleg_deg": dogleg, "curve_length": radius * phi,
                "max_inc_on_arc": peak})
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


# ---- M106: multi-target and S-profile solvers --------------------------------------------------------------
MULTI_SOLVER_VERSION = "M106 multi-target / S-profile solver v1"
TARGET_TOLERANCE_M = 0.01
SOLVER_OBJECTIVE = (
    "Pass through every target centre, in order, with constant-curvature arcs at the stated rates and tangent "
    "holds. Nothing is minimised (MD, dogleg, torque, cost): the result is one feasible profile, not an optimum."
)
SOLVER_CONVERGENCE = (
    "Closed form, no iteration. Acceptance: the segments are re-computed by the canonical minimum-curvature "
    f"engine and every target centre must lie within {TARGET_TOLERANCE_M} m of the continuous path, at the "
    "expected MD (order kept); otherwise the solve fails with NOT_CONVERGED."
)


def _finite(*values) -> bool:
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)


def _full_tie_in(tie_in: Optional[Dict[str, float]]) -> Dict[str, float]:
    """The tie-in as ``solve_build_hold`` reads it: TVD defaults to MD, N/E to 0 (vertical from surface)."""
    tie_in = dict(tie_in or {})
    md = float(tie_in.get("md", 0.0))
    return {"md": md, "inc": float(tie_in.get("inc", 0.0)), "azi": float(tie_in.get("azi", 0.0)),
            "tvd": float(tie_in.get("tvd", md)), "north": float(tie_in.get("north", 0.0)),
            "east": float(tie_in.get("east", 0.0))}


def _verify(out: Dict[str, Any], segments, tie_in, targets, expected_mds, step: float) -> Dict[str, Any]:
    """Re-compute with the canonical engine; every centre within the tolerance at its expected MD."""
    plan = design_plan(segments, step=step, tie_in=tie_in)
    rows, converged = [], plan.ok
    if not plan.ok:
        out["verification"] = {"converged": False, "tolerance_m": TARGET_TOLERANCE_M, "targets": [],
                               "error": plan.error}
        return _fail(out, "NOT_CONVERGED", f"The canonical engine rejected the solved segments: {plan.error}")
    for target, expected in zip(targets, expected_mds):
        near = closest_on_path(plan.stations, (float(target["north"]), float(target["east"]), float(target["tvd"])))
        ok = near["distance"] <= TARGET_TOLERANCE_M and abs(near["md"] - expected) <= max(1.0, step)
        converged = converged and ok
        rows.append({"name": target.get("name", "Target"), "distance": near["distance"], "closest_md": near["md"],
                     "expected_md": expected, "ok": ok})
    out["verification"] = {"converged": converged, "tolerance_m": TARGET_TOLERANCE_M, "targets": rows,
                           "td_md": plan.stations[-1]["md"], "max_dls": max(
                               (s.get("dls", 0.0) or 0.0 for s in plan.stations), default=0.0)}
    if not converged:
        worst = max(rows, key=lambda r: r["distance"]) if rows else None
        return _fail(out, "NOT_CONVERGED",
                     f"Target {worst['name']} is {worst['distance']:.4f} m from the re-computed path "
                     f"(tolerance {TARGET_TOLERANCE_M} m)." if worst else "No target could be verified.")
    return out


def solve_multi_target(targets: Sequence[Dict[str, Any]], *, kop_md: float, dls, tie_in=None,
                       max_inc: float = 90.0, dls_limit: Optional[float] = None, hold_after=0.0,
                       step: float = 30.0) -> Dict[str, Any]:
    """Curve-hold legs chained through several targets (build, drop, hold and turn in 3D).

    Leg 1 holds the tie-in direction to the KOP, then one constant-curvature arc and a tangent reach target 1's
    centre (the M86 closed form). Each later leg starts at the previous target, in the direction the well
    arrives with, optionally after ``hold_after`` metres, and repeats the construction towards the next
    target; the arc lies in the plane of that direction and the next target, so it builds, drops and turns as
    needed. ``dls`` is one rate (deg/30 m) or one per leg. A rate above ``dls_limit`` or an inclination above
    ``max_inc`` anywhere on an arc makes the solve infeasible (never clipped). Objective and acceptance:
    ``SOLVER_OBJECTIVE`` and ``SOLVER_CONVERGENCE``. Planning aid.
    """
    out: Dict[str, Any] = {"feasible": False, "method": MULTI_SOLVER_VERSION, "objective": SOLVER_OBJECTIVE,
                           "convergence": SOLVER_CONVERGENCE, "segments": [], "legs": [], "code": "",
                           "reason": ""}
    targets = list(targets or [])
    if not targets:
        return _fail(out, "NO_TARGETS", "Add at least one target.")
    rates = list(dls) if isinstance(dls, (list, tuple)) else [dls] * len(targets)
    holds = list(hold_after) if isinstance(hold_after, (list, tuple)) else [hold_after] * len(targets)
    if len(rates) != len(targets) or len(holds) < len(targets) - 1:
        return _fail(out, "INVALID_INPUT", "Give one build rate per leg and one hold-after length per target.")
    if not _finite(kop_md, max_inc, step, *rates, *holds[:len(targets)]) or (
            dls_limit is not None and not _finite(dls_limit)):
        return _fail(out, "INVALID_INPUT", "KOP, rates, holds, limits and the station step must be finite numbers.")
    if any(h < 0 for h in holds[:len(targets)]):
        return _fail(out, "INVALID_INPUT", "A hold-after length cannot be negative.")
    if step <= 0:
        return _fail(out, "INVALID_INPUT", "The station step must be positive.")
    if dls_limit is not None:
        for number, rate in enumerate(rates, 1):
            if rate > dls_limit + 1e-9:
                out["failed_leg"] = number
                return _fail(out, "DLS_LIMIT", f"Leg {number}: the rate {rate:g} deg/30 m exceeds the DLS limit "
                                               f"{dls_limit:g} deg/30 m.")
    start = _full_tie_in(tie_in)
    state, kop, segments, expected = dict(start), float(kop_md), [], []
    for number, target in enumerate(targets, 1):
        name = target.get("name") or f"target {number}"
        answer = solve_build_hold(target, kop_md=kop, dls=rates[number - 1], tie_in=state, max_inc=max_inc)
        if not answer["feasible"]:
            out["failed_leg"] = number
            return _fail(out, answer["code"], f"Leg {number} ({name}): {answer['reason']}")
        target_md = kop + answer["curve_length"] + answer["hold_length"]
        segments.extend(answer["segments"])
        expected.append(target_md)
        out["legs"].append({"number": number, "target": name, "start_md": state["md"], "kop_md": kop,
                            "target_md": target_md, "dls": rates[number - 1], "inc": answer["inc"],
                            "azi": answer["azi"], "dogleg_deg": answer["dogleg_deg"],
                            "curve_length": answer["curve_length"], "hold_length": answer["hold_length"],
                            "max_inc_on_arc": answer["max_inc_on_arc"]})
        state = {"md": target_md, "inc": answer["inc"], "azi": answer["azi"], "tvd": float(target["tvd"]),
                 "north": float(target["north"]), "east": float(target["east"])}
        kop = target_md + (float(holds[number - 1]) if number < len(targets) else 0.0)
    out.update({"segments": segments, "td_md": expected[-1]})
    _verify(out, segments, start, targets, expected, step)
    if out.get("code") == "NOT_CONVERGED":
        return out
    out.update({"feasible": True, "code": "OK", "reason": ""})
    return out


def solve_s_profile(target: Dict[str, Any], *, kop_md: float, build_dls: float, drop_dls: float,
                    final_inc: float = 0.0, final_hold: float = 0.0, tie_in=None, max_inc: float = 90.0,
                    dls_limit: Optional[float] = None, step: float = 30.0) -> Dict[str, Any]:
    """S-profile: vertical to the KOP, build, tangent, drop to ``final_inc``, final hold into the target centre.

    In the vertical plane of the target azimuth (X horizontal, Z down from the KOP), with R1 and R2 the build
    and drop radii, theta the tangent inclination, L the tangent and Lf the final hold at theta_f:
    X = R1(1 - cos theta) + L sin theta + R2(cos theta_f - cos theta) + Lf sin theta_f and
    Z = R1 sin theta + L cos theta + R2(sin theta - sin theta_f) + Lf cos theta_f.
    With A = X - Lf sin theta_f - R1 - R2 cos theta_f, B = Z - Lf cos theta_f + R2 sin theta_f, Rs = R1 + R2,
    rho = hypot(A, B) and alpha = atan2(A, B): theta = alpha + asin(Rs/rho), L = sqrt(rho^2 - Rs^2).
    The tie-in must be vertical (an inclined tie-in is NOT SUPPORTED here; use ``solve_multi_target``).
    Infeasible: rho < Rs (target too close for the rates), theta not above theta_f (no drop), theta above
    ``max_inc``, a rate above ``dls_limit``, no horizontal displacement. Planning aid; no optimality claim.
    """
    out: Dict[str, Any] = {"feasible": False, "method": MULTI_SOLVER_VERSION, "objective": SOLVER_OBJECTIVE,
                           "convergence": SOLVER_CONVERGENCE, "segments": [], "code": "", "reason": ""}
    values = [kop_md, build_dls, drop_dls, final_inc, final_hold, max_inc, step]
    values += [target.get(k) for k in ("tvd", "north", "east")]
    if not _finite(*values) or (dls_limit is not None and not _finite(dls_limit)) or (
            tie_in and not _finite(*(v for v in tie_in.values() if not isinstance(v, str)))):
        return _fail(out, "INVALID_INPUT", "Target, KOP, rates, final inclination/hold and limits must be finite.")
    start = _full_tie_in(tie_in)
    if start["inc"] > 1e-9:
        return _fail(out, "NOT_SUPPORTED", "The S-profile solver needs a vertical tie-in; use the multi-target "
                                           "solver from an inclined tie-in.")
    if build_dls <= 0 or drop_dls <= 0:
        return _fail(out, "NON_POSITIVE_RATE", "The build and drop rates must be positive.")
    if step <= 0 or final_hold < 0 or not 0.0 <= final_inc < 90.0:
        return _fail(out, "INVALID_INPUT", "Step must be positive, the final hold non-negative and the final "
                                           "inclination within 0-90 deg.")
    if kop_md < start["md"]:
        return _fail(out, "KOP_ABOVE_TIE_IN", f"The KOP {kop_md:g} m is above the tie-in MD {start['md']:g} m.")
    for label, rate in (("build", build_dls), ("drop", drop_dls)):
        if dls_limit is not None and rate > dls_limit + 1e-9:
            return _fail(out, "DLS_LIMIT", f"The {label} rate {rate:g} deg/30 m exceeds the DLS limit "
                                           f"{dls_limit:g} deg/30 m.")
    lead = kop_md - start["md"]
    p0 = (start["north"], start["east"], start["tvd"] + lead)
    dn, de, dz = float(target["north"]) - p0[0], float(target["east"]) - p0[1], float(target["tvd"]) - p0[2]
    x = math.hypot(dn, de)
    if x <= 1e-9:
        return _fail(out, "NO_DISPLACEMENT", "The target is directly below the KOP; an S-profile needs a "
                                             "horizontal displacement.")
    if dz <= 0:
        return _fail(out, "TARGET_NOT_BELOW_KOP", "The target is not below the KOP.")
    azi = math.degrees(math.atan2(de, dn)) % 360.0
    r1, r2 = 5400.0 / (math.pi * build_dls), 5400.0 / (math.pi * drop_dls)
    tf = math.radians(final_inc)
    a = x - final_hold * math.sin(tf) - r1 - r2 * math.cos(tf)
    b = dz - final_hold * math.cos(tf) + r2 * math.sin(tf)
    rs, rho = r1 + r2, math.hypot(a, b)
    out.update({"build_radius": r1, "drop_radius": r2, "azi": azi, "horizontal_offset": x, "kop_tvd": p0[2]})
    if rho < rs:
        return _fail(out, "INSIDE_TURN_RADIUS", f"Infeasible: the target is too close for build radius {r1:.1f} m "
                                                f"plus drop radius {r2:.1f} m; lower the rates or move the KOP up.")
    theta = math.atan2(a, b) + math.asin(rs / rho)
    tangent = math.sqrt(max(rho * rho - rs * rs, 0.0))
    peak = math.degrees(theta)
    if peak <= final_inc + 1e-9:
        return _fail(out, "NO_DROP", f"Infeasible: the tangent inclination {peak:.2f} deg is not above the final "
                                     f"inclination {final_inc:g} deg (this target needs a build-hold, not an S).")
    if peak >= 180.0 - 1e-9 or peak > max_inc + 1e-9:
        return _fail(out, "INC_LIMIT", f"Infeasible: the tangent inclination {peak:.2f} deg exceeds the limit "
                                       f"{max_inc:g} deg.")
    segments = []
    if lead > 1e-9:
        segments.append({"type": "hold", "length": lead})
    segments.append({"type": "curve", "inc": peak, "azi": azi, "dls": float(build_dls)})
    if tangent > 1e-9:
        segments.append({"type": "hold", "length": tangent})
    segments.append({"type": "curve", "inc": float(final_inc), "azi": azi, "dls": float(drop_dls)})
    if final_hold > 1e-9:
        segments.append({"type": "hold", "length": float(final_hold)})
    build_len = r1 * theta
    drop_len = r2 * (theta - tf)
    td = kop_md + build_len + tangent + drop_len + final_hold
    out.update({"segments": segments, "inc": peak, "hold_length": tangent, "build_length": build_len,
                "drop_length": drop_len, "final_inc": float(final_inc), "final_hold": float(final_hold),
                "td_md": td})
    _verify(out, segments, start, [target], [td], step)
    if out.get("code") == "NOT_CONVERGED":
        return out
    out.update({"feasible": True, "code": "OK", "reason": ""})
    return out
