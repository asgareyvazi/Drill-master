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

Targets ``{"name", "north", "east", "tvd", "radius"}`` are evaluated against the
plan stations (closest station distance, within radius or not). A segment above
the DLS limit is reported, never silently clipped. Planning aid only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

PLAN_VERSION = "M55 plan designer v1"
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
            current = TrajectoryCalculator.calculate([dict(s) for s in raw], vs_azimuth=vs_azimuth)[-1]["tvd"]
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
    result.stations = TrajectoryCalculator.calculate(raw, vs_azimuth=vs_azimuth)
    for target in targets:
        best = min(result.stations, key=lambda s: math.dist((s["north"], s["east"], s["tvd"]),
                                                             (target["north"], target["east"], target["tvd"])))
        distance = math.dist((best["north"], best["east"], best["tvd"]), (target["north"], target["east"], target["tvd"]))
        radius = float(target.get("radius", 0) or 0)
        result.targets.append({"name": target.get("name", "Target"), "closest_md": best["md"], "distance": distance,
                               "radius": radius, "hit": radius > 0 and distance <= radius})
    return result
