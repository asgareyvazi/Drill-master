"""Whole-well trajectory composition from persisted survey stations (M44).

Why this exists
---------------
Survey stations are stored per daily report, and the derived columns
(``tvd/north/east/vs/hd/dls``) of each report are calculated from that
report's stations alone: the engine places the report's first station at
N = E = 0 with TVD = MD x cos(inc).  Stored derived values from different
reports are therefore NOT in one coordinate frame, and successive reports
usually repeat the last station of the previous one.  A well-level view built
from the stored columns mixes frames and duplicates.

This module rebuilds the well trajectory from the *measured* inputs only
(MD, inclination, azimuth) and recomputes it once with the existing
``TrajectoryCalculator`` (minimum curvature).  It adds no new survey formula.

Rules (all deterministic, no guessing):

* rows with a missing, non-finite or negative MD are excluded and reported;
* rows with a missing angle, a non-finite angle or an inclination outside
  0..180 deg are excluded and reported;
* stations whose MD agrees within ``md_tolerance`` are one station when
  inclination and azimuth also agree within ``angle_tolerance`` (azimuth is
  compared on the circle); their sources are kept.  If they disagree the
  station is a *conflict*: every reading at that MD is excluded and the result
  needs review.  The module never picks one reading over another;
* the first usable station is tied on with the engine's documented assumption
  (N = E = 0, TVD = MD x cos(inc)), reported as an ``info`` issue;
* the vertical-section azimuth is either supplied by the user or, by default,
  the closure azimuth of the last station.  For a closure distance below
  ``closure_epsilon`` the azimuth is undefined and 0 deg (north) is used, and
  the result says so.

Not supported (and not claimed): survey error models / ISCWSA uncertainty,
grid convergence or map projections, magnetic-to-true corrections, tie-ons
to a deeper reference survey.

Units: lengths are the stored canonical metres; angles degrees; DLS
deg/30 m.  ``to_display_units`` converts for presentation only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Optional

FT_PER_M = 1.0 / 0.3048            # international foot, exact definition
DLS_30M_TO_100FT = 30.48 / 30.0    # 100 ft = 30.48 m exactly

NO_DATA = "NO_DATA"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
READY = "READY"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
ERROR = "ERROR"


@dataclass(frozen=True)
class TrajectoryIssue:
    code: str
    severity: str                 # "info" | "warning" | "error"
    message: str
    md: Optional[float] = None
    survey_ids: tuple = ()


@dataclass(frozen=True)
class ComposedStation:
    md: float
    inc: float
    azi: float
    tvd: float
    north: float
    east: float
    vs: float
    hd: float
    dls: float
    survey_ids: tuple = ()
    report_ids: tuple = ()
    tool: Optional[str] = None


@dataclass
class WellTrajectory:
    status: str
    stations: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    vs_azimuth: Optional[float] = None
    vs_azimuth_source: str = "none"     # "user" | "closure" | "default_north" | "none"
    closure_distance: Optional[float] = None
    closure_azimuth: Optional[float] = None
    input_rows: int = 0
    excluded_rows: int = 0

    @property
    def drawable(self) -> bool:
        """A path can be drawn only from two or more computed stations."""
        return len(self.stations) >= 2 and self.status in (READY, REVIEW_REQUIRED)

    def issues_at_least(self, severity: str) -> list:
        order = {"info": 0, "warning": 1, "error": 2}
        return [i for i in self.issues if order[i.severity] >= order[severity]]


def _finite(value) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):  # silent-ok: unparsable input is missing (None), reported as an issue by the caller
        return None
    return number if math.isfinite(number) else None


def _get(row, key):
    return row.get(key) if isinstance(row, dict) else getattr(row, key, None)


def _azimuth_difference(a: float, b: float) -> float:
    diff = abs((a - b) % 360.0)
    return min(diff, 360.0 - diff)


def _normalise_azimuth(value: float) -> float:
    result = value % 360.0
    return 0.0 if math.isclose(result, 360.0) else result


def compose_well_trajectory(rows: Iterable, *, vs_azimuth: Optional[float] = None,
                            md_tolerance: float = 0.01, angle_tolerance: float = 0.01,
                            closure_epsilon: float = 0.01,
                            large_gap_m: float = 150.0) -> WellTrajectory:
    """Compose one trajectory from survey rows (dicts or ORM objects)."""
    rows = list(rows or [])
    result = WellTrajectory(status=NO_DATA, input_rows=len(rows))
    if not rows:
        return result

    candidates = []
    for row in rows:
        survey_id = _get(row, "id")
        ids = (survey_id,) if survey_id is not None else ()
        md = _finite(_get(row, "md"))
        if md is None or md < 0:
            result.issues.append(TrajectoryIssue(
                "INVALID_MD", "warning", "Station excluded: measured depth is missing, not a number or negative",
                survey_ids=ids))
            continue
        raw_inc, raw_azi = _get(row, "inc"), _get(row, "azi")
        if raw_inc is None or raw_azi is None:
            result.issues.append(TrajectoryIssue(
                "MISSING_ANGLE", "warning", "Station excluded: inclination or azimuth not reported",
                md=md, survey_ids=ids))
            continue
        inc, azi = _finite(raw_inc), _finite(raw_azi)
        if inc is None or azi is None or not 0.0 <= inc <= 180.0:
            result.issues.append(TrajectoryIssue(
                "INVALID_ANGLE", "warning",
                "Station excluded: inclination must be 0-180 deg and azimuth a finite number",
                md=md, survey_ids=ids))
            continue
        candidates.append({"md": md, "inc": inc, "azi": _normalise_azimuth(azi), "ids": ids,
                           "report_id": _get(row, "report_id"), "tool": _get(row, "tool")})

    result.excluded_rows = len(rows) - len(candidates)
    candidates.sort(key=lambda c: (c["md"], c["ids"]))

    groups: list = []
    for candidate in candidates:
        if groups and candidate["md"] - groups[-1][0]["md"] <= md_tolerance:
            groups[-1].append(candidate)
        else:
            groups.append([candidate])

    stations = []
    conflicts = 0
    for group in groups:
        first = group[0]
        agree = all(abs(c["inc"] - first["inc"]) <= angle_tolerance
                    and _azimuth_difference(c["azi"], first["azi"]) <= angle_tolerance for c in group)
        ids = tuple(i for c in group for i in c["ids"])
        if not agree:
            conflicts += 1
            result.excluded_rows += len(group)
            result.issues.append(TrajectoryIssue(
                "CONFLICTING_DUPLICATE", "error",
                f"{len(group)} readings at the same MD disagree on inclination/azimuth; "
                "all excluded until reviewed", md=first["md"], survey_ids=ids))
            continue
        report_ids = tuple(sorted({c["report_id"] for c in group if c["report_id"] is not None}))
        stations.append({"md": first["md"], "inc": first["inc"], "azi": first["azi"],
                         "ids": ids, "report_ids": report_ids, "tool": first["tool"]})

    if not stations:
        result.status = INSUFFICIENT_DATA
        return result

    from core.engineering.result import EngineeringError
    from core.engineering.engines.trajectory import TrajectoryCalculator

    inputs = [{"md": s["md"], "inc": s["inc"], "azi": s["azi"]} for s in stations]
    try:
        provisional = TrajectoryCalculator.calculate(inputs, vs_azimuth=0.0)
        last = provisional[-1]
        closure = math.hypot(last["north"], last["east"])
        result.closure_distance = closure
        if closure >= closure_epsilon:
            result.closure_azimuth = _normalise_azimuth(math.degrees(math.atan2(last["east"], last["north"])))
        user_azimuth = _finite(vs_azimuth)
        if user_azimuth is not None:
            result.vs_azimuth, result.vs_azimuth_source = _normalise_azimuth(user_azimuth), "user"
        elif result.closure_azimuth is not None:
            result.vs_azimuth, result.vs_azimuth_source = result.closure_azimuth, "closure"
        else:
            result.vs_azimuth, result.vs_azimuth_source = 0.0, "default_north"
            result.issues.append(TrajectoryIssue(
                "VS_AZIMUTH_UNDEFINED", "info",
                "Closure distance is below 0.01 m; vertical-section azimuth set to 0 deg (north)"))
        computed = TrajectoryCalculator.calculate(inputs, vs_azimuth=result.vs_azimuth)
    except EngineeringError as exc:
        result.status = ERROR
        result.issues.append(TrajectoryIssue("ENGINE_REFUSED", "error",
                                             f"Trajectory engine refused the stations ({type(exc).__name__})"))
        return result

    for source, point in zip(stations, computed):
        result.stations.append(ComposedStation(
            md=point["md"], inc=point["inc"], azi=point["azi"], tvd=point["tvd"],
            north=point["north"], east=point["east"], vs=point["vs"], hd=point["hd"],
            dls=point["dls"], survey_ids=source["ids"], report_ids=source["report_ids"],
            tool=source["tool"]))

    first = result.stations[0]
    result.issues.append(TrajectoryIssue(
        "TIE_ON_ASSUMED", "info",
        f"Tie-on at the first station (MD {first.md:.2f} m): N = E = 0 and TVD = MD x cos(inc), "
        "the engine's surface-origin assumption", md=first.md))
    for previous, current in zip(result.stations, result.stations[1:]):
        if current.md - previous.md > large_gap_m:
            result.issues.append(TrajectoryIssue(
                "LARGE_STATION_GAP", "warning",
                f"{current.md - previous.md:.1f} m between stations; minimum curvature interpolates "
                "the gap and may not represent the drilled path", md=current.md))

    if len(result.stations) < 2:
        result.status = INSUFFICIENT_DATA
    elif conflicts or result.excluded_rows:
        result.status = REVIEW_REQUIRED
    else:
        result.status = READY
    return result


def to_display_units(value: Optional[float], unit: str) -> Optional[float]:
    """Convert a stored metre length for display ("m" or "ft")."""
    if value is None:
        return None
    if unit == "m":
        return value
    if unit == "ft":
        return value * FT_PER_M
    raise ValueError(f"Unsupported length unit {unit!r}")


def dls_for_display(value: Optional[float], unit: str) -> Optional[float]:
    """Convert stored deg/30 m dogleg severity ("deg/30m" or "deg/100ft")."""
    if value is None:
        return None
    if unit == "deg/30m":
        return value
    if unit == "deg/100ft":
        return value * DLS_30M_TO_100FT
    raise ValueError(f"Unsupported DLS unit {unit!r}")


def load_well_trajectory(db_manager, well_id: int, *, report_id: Optional[int] = None,
                         vs_azimuth: Optional[float] = None) -> WellTrajectory:
    """Read the stations of a well (optionally one report) and compose them."""
    rows = db_manager.load_survey_points(well_id=well_id, report_id=report_id) if well_id else []
    return compose_well_trajectory(rows, vs_azimuth=vs_azimuth)
