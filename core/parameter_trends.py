"""M131: drilling-parameter trend workspace (DDR drilling parameters and saved MSE runs).

Rules (each is tested):

* **One axis per view**, chosen explicitly: report date (DDR) or depth out (m MD, DDR). Time and depth are
  never mixed in one view; a row without a value for the chosen axis is listed as *not placed*, never put
  at a guessed position.
* **No interpolation, no fabricated value.** Min / max parameters are shown as the recorded range (a single
  recorded bound is shown as that bound and named, never as a midpoint); a missing value is listed with its
  date and source row; an inverted range (min > max) or a negative value is INVALID and listed.
  The panel draws markers and range bars only - no line joins two records.
* **MSE is not a continuous log.** Saved MSE runs are discrete points: on the depth axis only with a
  recorded (or audited-repair) MD, on the time axis only when linked to a DDR of the well (the save time is
  not a drilling time); others are listed as not placed with their lineage class.
* **Scope**: one well, or only the DDRs / MSE runs of an explicitly selected wellbore (unscoped legacy MSE runs
  are excluded from a wellbore view and counted).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple

TREND_METHOD = "M131 drilling-parameter trends v1"
AXIS_TIME, AXIS_DEPTH = "time", "depth"
AXIS_LABELS = {AXIS_TIME: "Report date (DDR)", AXIS_DEPTH: "Depth out (m MD, DDR)"}
MSE_LABEL = "MSE — discrete saved runs, not a continuous log"

# key, label, unit, low attribute, high attribute (units as imported: core/canonical_schema.py drilling_params)
PARAMETERS: Tuple[Tuple[str, str, str, str, str], ...] = (
    ("rop", "ROP (average)", "m/h", "avg_rop", "avg_rop"),
    ("wob", "WOB", "klb", "wob_min", "wob_max"),
    ("rpm", "Surface RPM", "rpm", "rpm_min", "rpm_max"),
    ("torque", "Torque", "kft·lbf", "torque_min", "torque_max"),
    ("spp", "Pump pressure", "psi", "pump_pressure_min", "pump_pressure_max"),
    ("flow", "Pump output", "gpm", "pump_output_min", "pump_output_max"),
)
PARAMETER_KEYS = tuple(p[0] for p in PARAMETERS)


@dataclass(frozen=True)
class TrendPoint:
    x: Any                    # a date (time axis) or metres MD (depth axis)
    low: Optional[float]
    high: Optional[float]
    note: str                 # "" | "only min recorded" | "only max recorded"
    date: Optional[date]
    depth_out: Optional[float]
    bit: str
    source: str               # "drilling_parameters #id" or "mse_calculations #id"
    report_id: Optional[int] = None


@dataclass
class Series:
    key: str
    label: str
    unit: str
    points: List[TrendPoint] = field(default_factory=list)
    missing: List[Tuple[Any, str]] = field(default_factory=list)       # (date, source)
    invalid: List[Tuple[Any, str, str]] = field(default_factory=list)  # (date, source, reason)
    not_placed: List[Tuple[Any, str, str]] = field(default_factory=list)

    def summary(self) -> str:
        return (f"{self.label} ({self.unit}): {len(self.points)} placed, {len(self.missing)} missing, "
                f"{len(self.invalid)} invalid, {len(self.not_placed)} not placed")


@dataclass
class TrendResult:
    axis: str
    axis_label: str
    series: Dict[str, Series]
    mse: Series
    rows: int
    scope_label: str = ""
    method: str = TREND_METHOD
    excluded_mse: List[Tuple[Any, str, str]] = field(default_factory=list)


def _value(raw) -> Tuple[str, Optional[float]]:
    from core import analysis_evidence as ev

    state, number, _reason = ev.classify_number(raw)
    if state == ev.STATE_VALUE:
        return "value", number
    if state == ev.STATE_MISSING:
        return "missing", None
    return "invalid", None


def build(params: Sequence[Any], axis: str, mse_runs: Sequence[Any] = (), report_dates: Optional[Dict] = None,
          wellbore_id: Optional[int] = None, scope_label: str = "") -> TrendResult:
    """``params``: DDR drilling-parameter rows (attributes as the model); ``mse_runs``: saved MSE runs."""
    if axis not in AXIS_LABELS:
        raise ValueError(f"unknown axis {axis!r}; choose {', '.join(AXIS_LABELS)}")
    series = {key: Series(key, label, unit) for key, label, unit, _lo, _hi in PARAMETERS}
    for p in params:
        source = f"drilling_parameters #{p.id}"
        x = p.report_date if axis == AXIS_TIME else _value(p.depth_out)[1]
        for key, _label, _unit, low_attr, high_attr in PARAMETERS:
            s = series[key]
            (ls, low), (hs, high) = _value(getattr(p, low_attr)), _value(getattr(p, high_attr))
            if "invalid" in (ls, hs):
                s.invalid.append((p.report_date, source, "negative or non-numeric value"))
                continue
            if low is None and high is None:
                s.missing.append((p.report_date, source))
                continue
            if low is not None and high is not None and low > high:
                s.invalid.append((p.report_date, source, f"min {low:g} > max {high:g}"))
                continue
            if x is None:
                s.not_placed.append((p.report_date, source, _not_placed_reason(p, axis)))
                continue
            note = "" if low_attr == high_attr or (low is not None and high is not None) else \
                ("only min recorded" if high is None else "only max recorded")
            s.points.append(TrendPoint(x, low, high, note, p.report_date, _value(p.depth_out)[1],
                                       (p.bit_no or "").strip(), source, p.report_id))
    for s in series.values():
        s.points.sort(key=lambda pt: (pt.x, pt.source))
    mse, excluded = _mse_series(mse_runs, axis, report_dates or {}, wellbore_id)
    return TrendResult(axis, AXIS_LABELS[axis], series, mse, len(params), scope_label, excluded_mse=excluded)


def _not_placed_reason(p, axis: str) -> str:
    """M140: a recorded but unusable depth is not called "not recorded"."""
    if axis != AXIS_DEPTH:
        return "no report date"
    state, _number = _value(p.depth_out)
    return "depth out not recorded" if state == "missing" else "depth out invalid (negative or non-numeric)"


def _mse_series(runs, axis, report_dates, wellbore_id):
    from core.repositories.mse_repository import LEGACY_LABEL

    s = Series("mse", MSE_LABEL, "psi")
    excluded = []
    for run in runs:
        source = f"mse_calculations #{run.id}"
        lineage = LEGACY_LABEL if run.is_legacy else run.lineage_class     # D6: one legacy label
        if wellbore_id and run.effective_wellbore_id != wellbore_id:
            excluded.append((run.created_at, source, f"not recorded for this wellbore ({lineage})"))
            continue
        value = run.stored_mse_psi
        if value is None:
            s.missing.append((run.created_at, source))
            continue
        report = run.effective_report_id
        day = report_dates.get(report)
        if axis == AXIS_DEPTH:
            x = run.effective_md_m
            reason = f"no recorded MD ({lineage})"
        else:
            x = day
            reason = (f"not linked to a DDR of this well (saved {run.created_at:%Y-%m-%d}; the save time is not a "
                      f"drilling time; {lineage})" if run.created_at else f"not linked to a DDR ({lineage})")
        if x is None:
            s.not_placed.append((run.created_at, source, reason))
            continue
        note = "repaired lineage: " + ", ".join(run.repaired_fields) if run.repaired_fields else ""
        s.points.append(TrendPoint(x, value, value, note, day, run.effective_md_m, "", source, report))
    s.points.sort(key=lambda pt: (pt.x, pt.source))
    return s, excluded


def load(db, well_id: int, axis: str, wellbore_id: Optional[int] = None) -> TrendResult:
    from core.database import DailyReport, DrillingParameters
    from core.operations_intelligence import canonical_params_clause
    from core.repositories.mse_repository import runs_for_well

    with db.session_scope() as session:
        reports = session.query(DailyReport.id, DailyReport.report_date, DailyReport.wellbore_id) \
            .filter(DailyReport.well_id == well_id).all()
        report_dates = {rid: day for rid, day, _bore in reports}
        query = session.query(DrillingParameters).filter(DrillingParameters.well_id == well_id)
        if wellbore_id:
            ids = [rid for rid, _day, bore in reports if bore == wellbore_id]
            query = query.filter(DrillingParameters.report_id.in_(ids or [-1]))
            report_dates = {rid: day for rid, day, bore in reports if bore == wellbore_id}
        else:
            query = query.filter(canonical_params_clause(DrillingParameters))
        params = query.order_by(DrillingParameters.report_date, DrillingParameters.id).all()
        for p in params:
            session.expunge(p)
        runs = runs_for_well(session, well_id)
    scope = f"Well #{well_id}" + (f", wellbore #{wellbore_id} only" if wellbore_id else ", whole well")
    return build(params, axis, runs, report_dates, wellbore_id, scope)


def export_csv(path: str, result: TrendResult) -> int:
    """Every placed point, missing, invalid and not-placed row with its source; returns the placed count."""
    placed = 0
    with open(path, "w", newline="", encoding="utf-8") as handle:
        out = csv.writer(handle)
        out.writerow(["Drilling-parameter trends", result.method])
        out.writerow(["Scope", result.scope_label])
        out.writerow(["Axis", result.axis_label])
        out.writerow(["Rule", "markers and recorded ranges only; no interpolation; unknown values are empty"])
        out.writerow([])
        out.writerow(["Parameter", "Unit", "State", "X", "Min / value", "Max", "Note", "Date", "Depth out (m)",
                      "Bit", "Source"])
        for s in list(result.series.values()) + [result.mse]:
            for pt in s.points:
                placed += 1
                out.writerow([s.label, s.unit, "placed", pt.x, _blank(pt.low), _blank(pt.high), pt.note,
                              _blank(pt.date), _blank(pt.depth_out), pt.bit, pt.source])
            for day, source in s.missing:
                out.writerow([s.label, s.unit, "missing", "", "", "", "", _blank(day), "", "", source])
            for day, source, reason in s.invalid:
                out.writerow([s.label, s.unit, "INVALID", "", "", "", reason, _blank(day), "", "", source])
            for day, source, reason in s.not_placed:
                out.writerow([s.label, s.unit, "not placed", "", "", "", reason, _blank(day), "", "", source])
        for day, source, reason in result.excluded_mse:
            out.writerow([result.mse.label, "psi", "excluded (scope)", "", "", "", reason, _blank(day), "", "",
                          source])
    return placed


def _blank(value):
    return "" if value is None else value
