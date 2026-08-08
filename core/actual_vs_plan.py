"""Actual-versus-plan metrics for monitoring and exports."""
from dataclasses import dataclass


@dataclass
class Variance:
    metric: str
    planned: float
    actual: float
    variance: float
    variance_pct: float
    status: str


def compare(metric, planned, actual, tolerance_pct=10.0):
    planned, actual = float(planned or 0), float(actual or 0)
    delta = actual - planned
    pct = (delta / planned * 100) if planned else (0.0 if actual == 0 else 100.0)
    # For progress/depth, being behind is negative; for hours/cost users
    # usually care about absolute overrun, so status is based on magnitude.
    status = "on-track" if abs(pct) <= tolerance_pct else ("ahead" if pct > 0 else "behind")
    return Variance(metric, planned, actual, delta, round(pct, 2), status)


def compare_plan_activities(activities, actual_depth=0, actual_hours=0):
    planned_hours = sum(float(a.get("planned_duration_hours", 0) or 0) for a in activities or [])
    planned_depth = max((float(a.get("planned_depth_to", 0) or 0) for a in activities or []), default=0)
    return [
        compare("Depth", planned_depth, actual_depth),
        compare("Hours", planned_hours, actual_hours),
    ]
