"""Recorded time reductions shared by analytics and exports (no Qt/DB writes)."""
from core.engineering.result import optional_number, EngineeringError


def summarize_time_logs(logs):
    """Unknown/invalid durations do not become zero or a complete denominator.

    A known subtotal is evidence, not the total. No rows means unknown, while
    recorded zero stays zero. A NULL NPT flag cannot prove productive time.
    """
    logs = list(logs)
    known_hours = known_npt = 0.0
    missing = missing_npt = 0
    classified = True
    for row in logs:
        try:
            duration = optional_number(row.duration, "duration")
        except EngineeringError:
            duration = None
        valid = duration is not None and duration >= 0
        if valid:
            known_hours += float(duration)
        else:
            missing += 1
        if row.is_npt is not True and row.is_npt is not False:
            classified = False
        elif row.is_npt is True:
            if valid:
                known_npt += float(duration)
            else:
                missing_npt += 1
    total = known_hours if logs and not missing else None
    npt = known_npt if logs and not missing_npt and classified else None
    productive = total - npt if total is not None and npt is not None else None
    percent = npt / total * 100 if total and npt is not None else None
    return {
        "total_hours": total, "npt_hours": npt,
        "productive_hours": productive, "npt_percent": percent,
        "known_hours": known_hours, "known_npt_hours": known_npt,
        "unknown_duration_count": missing, "unknown_npt_count": missing_npt,
    }
