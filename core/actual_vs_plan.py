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
    optional_number,
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
    planned = optional_number(planned, "planned")
    actual = optional_number(actual, "actual")
    tolerance_pct = require_number(tolerance_pct, "tolerance_pct")
    if tolerance_pct < 0:
        raise EngineeringError("tolerance_pct cannot be negative")
    if planned is None or actual is None:
        return Variance(metric, planned, actual, None, None, "unavailable")
    delta = require_number(actual - planned, "variance")
    # Preserve the established zero/zero equality convention; nonzero / zero
    # has a known delta but no finite percentage (never synthetic 100%).
    pct = delta / abs(planned) * 100 if planned else (0.0 if actual == 0 else None)
    pct = optional_number(pct, "variance_pct")
    status = ("unavailable" if pct is None else "on-track" if abs(pct) <= tolerance_pct
              else "ahead" if pct > 0 else "behind")
    return Variance(metric, planned, actual, delta, round(pct, 2) if pct is not None else None, status)



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
            unavailable = {}
            for key, label in cls.METRIC_LABELS.items():
                planned_value = planned.get(key)
                actual_value = actual.get(key)
                if planned_value in (None, "") or actual_value in (None, ""):
                    missing_metrics.append(key)
                    from dataclasses import asdict
                    unavailable[key] = asdict(compare(label, planned_value, actual_value, tolerance))
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
                result = missing("planned and actual metrics")
                result.metadata["unavailable_metrics"] = unavailable
                return result
            warnings = [
                f"Metric not compared because one side is missing: {key}"
                for key in missing_metrics
            ]
            return ok(
                values,
                values=values,
                unit="mixed metric units",
                formula="variance = actual − planned; variance_pct = variance / abs(planned) × 100",
                method=cls.METHOD,
                assumptions=[
                    "Only metrics explicitly present on both sides are compared",
                    "Tolerance is a reporting threshold, not an engineering limit",
                ],
                warnings=warnings,
                metadata={"tolerance_pct": tolerance, "unavailable_metrics": unavailable},
                scope=cls.SCOPE,
            )
        except MissingInputError as exc:
            return missing(exc.field)
        except EngineeringError as exc:
            return failed(str(exc))


def activity_plan_totals(activities):
    """Declared activity totals; incomplete data remains unknown, zero survives."""
    rows = list(activities or [])
    def values(key):
        return [optional_number(r.get(key) if isinstance(r, dict) else getattr(r, key), key) for r in rows]
    hours, depths = values("planned_duration_hours"), values("planned_depth_to")
    return {
        "hours": sum(hours) if hours and all(v is not None for v in hours) else None,
        "depth": max(depths) if depths and all(v is not None for v in depths) else None,
    }


def compare_plan_activities(activities, actual_depth=None, actual_hours=None):
    """Keep the list-of-Variance API without inventing absent plan/actual facts."""
    totals = activity_plan_totals(activities)
    return [compare("Depth", totals["depth"], actual_depth),
            compare("Hours", totals["hours"], actual_hours)]


def section_actual_days(session, section_id):
    """Complete recorded section time, not report count or a known subtotal."""
    from core.database import DailyReport, TimeLog24H
    from core.operational_time import summarize_time_logs
    logs = session.query(TimeLog24H).join(DailyReport, TimeLog24H.report_id == DailyReport.id).filter(
        DailyReport.section_id == section_id).all()
    hours = summarize_time_logs(logs)["total_hours"]
    return hours / 24 if hours is not None else None


def summarize_actual_vs_plan(plan, activities, reports, time_logs, drilling_params, cost_records):
    """Plan-vs-actual metrics from already-loaded records (no database access).

    Extracted unchanged from ``DatabaseManager.get_actual_vs_plan``, which
    keeps the queries and the session. Time, ROP and cost values come from
    persisted records only: a report count is not treated as 24 hours and a
    rig-day price is never invented here.
    """
    from core.operational_time import summarize_time_logs
    from core.cost_semantics import summarize_costs
    totals = activity_plan_totals(activities)
    planned_hours = totals["hours"] if activities else (
        plan.planned_total_days * 24 if plan and plan.planned_total_days is not None else None)
    planned_depth = totals["depth"] if activities else (plan.planned_final_depth if plan else None)

    depths = [float(r.depth_2400) for r in reports if r.depth_2400 is not None]
    actual_depth = max(depths) if depths else None
    time_metrics = summarize_time_logs(time_logs)
    actual_hours = time_metrics["total_hours"]
    actual_npt_hours = time_metrics["npt_hours"]

    actual_rops = [
        float(r.rop_meter) for r in reports
        if r.rop_meter is not None and float(r.rop_meter) >= 0
    ]
    if not actual_rops:
        actual_rops = [
            float(p.avg_rop) for p in drilling_params
            if p.avg_rop is not None and float(p.avg_rop) >= 0
        ]
    planned_rop = (
        planned_depth / planned_hours
        if planned_depth is not None and planned_hours else None
    )
    actual_rop = (
        sum(actual_rops) / len(actual_rops) if actual_rops else None
    )
    costs = summarize_costs(cost_records)
    planned_cost, actual_cost = costs["total_planned"], costs["total_actual"]

    comparison = ActualVsPlanEngine.compare_metrics(
        {
            "depth_m": planned_depth,
            "hours": planned_hours,
            "rop_m_per_hr": planned_rop,
            "cost": planned_cost,
        },
        {
            "depth_m": actual_depth,
            "hours": actual_hours,
            "rop_m_per_hr": actual_rop,
            "cost": actual_cost,
        },
    )

    def legacy_metric(key):
        item = comparison.values.get(key) or comparison.metadata.get("unavailable_metrics", {}).get(key)
        if item:
            return {
                "planned": item["planned"],
                "actual": item["actual"],
                "delta": item["variance"],
                "pct": item["variance_pct"],
                "status": item["status"],
            }
        return {
            "planned": None,
            "actual": None,
            "delta": None,
            "pct": None,
            "status": "unavailable",
        }

    return {
        "depth": legacy_metric("depth_m"),
        "hours": legacy_metric("hours"),
        "rop": legacy_metric("rop_m_per_hr"),
        "cost": dict(legacy_metric("cost"), currency=costs["currency"], currency_status=costs["status"]),
        "npt_hours": actual_npt_hours,
        "plan_id": plan.id if plan else None,
        "reports": len(reports),
        "warnings": comparison.warnings,
        "scope": comparison.scope,
    }
