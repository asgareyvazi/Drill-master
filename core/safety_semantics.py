"""Evidence-based SafetyReport reductions; absence is not a safe observation."""

from core.cost_semantics import complete_total


def safety_kpis(reports):
    reports = list(reports)
    latest = max((r.report_date for r in reports if r.report_date is not None), default=None)
    current = [r for r in reports if r.report_date == latest] if latest is not None else []
    return {
        "days_without_lti": current[0].days_without_lti if len(current) == 1 else None,
        "total_lti": complete_total(r.lti_count for r in reports),
        "total_near_miss": complete_total(r.near_miss_count for r in reports),
    }
