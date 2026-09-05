"""Deterministic actual-versus-plan metrics for monitoring and exports."""

from dataclasses import dataclass
from typing import Any, Dict

from core.engineering.result import (
    EngineeringError,
    EngineeringResult,
    MissingInputError,
    failed,
    missing,
    ok,
    require_number,
)


@dataclass
class Variance:
    metric: str
    planned: float
    actual: float
    variance: float
    variance_pct: float
    status: str


def compare(metric, planned, actual, tolerance_pct=10.0):
    """Backward-compatible scalar comparison used by existing operations tests."""
    planned, actual = float(planned or 0), float(actual or 0)
    delta = actual - planned
    pct = (delta / planned * 100) if planned else (0.0 if actual == 0 else 100.0)
    status = "on-track" if abs(pct) <= tolerance_pct else ("ahead" if pct > 0 else "behind")
    return Variance(metric, planned, actual, delta, round(pct, 2), status)


class ActualVsPlanEngine:
    """Canonical deterministic comparisons for metrics present in both datasets."""

    METHOD = "Deterministic actual-versus-plan variance"
    SCOPE = "COMPLETE"
    METRIC_LABELS = {
        "depth_m": "Depth",
        "hours": "Hours",
        "rop_m_per_hr": "ROP",
        "npt_hours": "NPT hours",
        "cost": "Cost",
    }

    @classmethod
    def compare_metrics(
        cls,
        planned: Dict[str, Any],
        actual: Dict[str, Any],
        *,
        tolerance_pct: float = 10.0,
    ) -> EngineeringResult:
        """Compare only explicitly supplied planned and actual values.

        Missing metrics are omitted and reported in ``warnings``; no value is
        fabricated from a default duration, rate, cost or depth.
        """
        try:
            if not isinstance(planned, dict):
                raise EngineeringError("planned must be a mapping")
            if not isinstance(actual, dict):
                raise EngineeringError("actual must be a mapping")
            tolerance = require_number(tolerance_pct, "tolerance_pct")
            if tolerance < 0:
                raise EngineeringError("tolerance_pct cannot be negative")

            values: Dict[str, Dict[str, Any]] = {}
            missing_metrics = []
            for key, label in cls.METRIC_LABELS.items():
                planned_value = planned.get(key)
                actual_value = actual.get(key)
                if planned_value in (None, "") or actual_value in (None, ""):
                    missing_metrics.append(key)
                    continue
                p = require_number(planned_value, f"planned.{key}")
                a = require_number(actual_value, f"actual.{key}")
                variance = compare(label, p, a, tolerance)
                values[key] = {
                    "metric": label,
                    "planned": variance.planned,
                    "actual": variance.actual,
                    "variance": variance.variance,
                    "variance_pct": variance.variance_pct,
                    "status": variance.status,
                }
            if not values:
                return missing("planned and actual metrics")
            warnings = [
                f"Metric not compared because one side is missing: {key}"
                for key in missing_metrics
            ]
            return ok(
                values,
                values=values,
                unit="mixed metric units",
                formula="variance = actual − planned; variance_pct = variance / planned × 100",
                method=cls.METHOD,
                assumptions=[
                    "Only metrics explicitly present on both sides are compared",
                    "Tolerance is a reporting threshold, not an engineering limit",
                ],
                warnings=warnings,
                metadata={"tolerance_pct": tolerance},
                scope=cls.SCOPE,
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))


def compare_plan_activities(activities, actual_depth=0, actual_hours=0):
    """Backward-compatible depth/hour comparison for planned activities."""
    planned_hours = sum(float(a.get("planned_duration_hours", 0) or 0) for a in activities or [])
    planned_depth = max((float(a.get("planned_depth_to", 0) or 0) for a in activities or []), default=0)
    return [
        compare("Depth", planned_depth, actual_depth),
        compare("Hours", planned_hours, actual_hours),
    ]
