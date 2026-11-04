"""M91: Operational Analysis - Qt-free and read-only.

One pass over the persisted records of an ``AnalysisScope`` (well, optionally a
wellbore) and an optional report-date range:

* **daily** - footage (depth 24:00 - depth 00:00), drilling / NPT / logged
  hours and the day's ROP = footage / drilling hours;
* **summary** - total footage, drilling hours and the *time-weighted* ROP
  sum(footage) / sum(drilling hours) over the days where both are known, NPT
  hours and percentage (``operational_time.summarize_time_logs`` semantics),
  costs per currency (``cost_semantics.summarize_costs``: no FX, no mixing);
* **activities** - logged hours per canonical activity through the existing
  ``ActivityMapper`` with its resolution method (explainable): "unresolved"
  stays visible and fuzzy matches are listed as UNCERTAIN; only exact, learned
  or description matches count as drilling time;
* **npt** - NPT timeline from the time logs and, as a separate source, the NPT
  register (never added together);
* **bit_runs** - DrillingParameters grouped by bit number and rerun;
* **mse** - stored MSE calculations in time order (no depth is stored, nothing
  is interpolated);
* **cost** - currency / category groups;
* **plan_vs_actual** - ``DatabaseManager.get_actual_vs_plan`` (whole well).

Rules: a missing value is ``None`` and is never shown or summed as 0; a
negative footage is INVALID with the reason; every table row carries its
source (table + id) and, where one exists, the daily-report id for the
drill-down. Depths are stored in metres in these tables (DEPTH_UNIT).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

from core import analysis_evidence as ev

OA_VERSION = "M104 operational analysis v2"
DEPTH_UNIT = "m"
LABEL = "UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED"
COMPLETE, PARTIAL, NOT_ASSESSED = "COMPLETE", "PARTIAL", "NOT ASSESSED"
from core.repositories.mse_repository import LEGACY_LABEL as LEGACY_LINEAGE  # M123: one legacy label
from core.repositories.mse_repository import runs_for_well as mse_runs_for_well
PLAN_UNITS = {"depth": "m", "hours": "h", "rop": "m/h", "cost": "currency of the cost records"}
DRILLING_ACTIVITY = "DRILLING"
TRUSTED_MAPPING = ("exact", "learned", "description")   # fuzzy matches are shown as UNCERTAIN, never drilling time

COLUMNS = {
    "kpis": ("KPI", "Value", "Unit", "Scope", "Source", "Quality", "Reason"),
    "daily": ("Date", "Report #", "Depth 00:00 (m)", "Depth 24:00 (m)", "Footage (m)", "Drilling h", "NPT h",
              "Logged h", "ROP (m/h)", "Notes", "Source"),
    "activities": ("Activity", "Codes", "Mapping", "Hours", "NPT h", "Logs", "Unknown durations"),
    "npt": ("Date", "From", "To", "Hours", "Category", "Code", "Description", "Source"),
    "bit_runs": ("Bit #", "Rerun", "Size (in)", "Type", "Depth in (m)", "Depth out (m)", "Footage (m)",
                 "Hours on bottom", "ROP (m/h)", "Footage basis", "Reports", "ROP basis", "Source"),
    "bit_rows": ("Bit #", "Rerun", "Date", "Report #", "Depth in (m)", "Depth out (m)", "Drilled (m)",
                 "Hours on bottom", "ROP (m/h)", "Notes", "Source"),
    "mse": ("Saved at (UTC)", "Label", "MSE (psi)", "WOB (lbf)", "RPM", "Torque (ft·lbf)", "ROP (ft/h)",
            "Bit (in)", "Wellbore", "Report #", "Input source", "Source", "Lineage class", "MD (m)",
            "Lineage repairs"),
    "cost": ("Currency", "Category", "Planned", "Actual", "Variance"),
    "plan_vs_actual": ("Metric", "Unit", "Planned", "Actual", "Delta", "Delta %", "Status", "Reason"),
}


@dataclass
class OperationalAnalysis:
    scope_label: str
    start: Optional[date]
    end: Optional[date]
    summary: Dict[str, Any]
    tables: Dict[str, Tuple[Sequence[str], List[list]]]
    report_ids: Dict[str, List[Optional[int]]]          # drill-down per table row
    notes: List[str] = field(default_factory=list)
    generated_at: str = ""
    version: str = OA_VERSION

    def metadata(self) -> Dict[str, Any]:
        return {"scope": self.scope_label, "from": self.start or "first report", "to": self.end or "last report",
                "generated_utc": self.generated_at, "method": self.version, "depth_unit": DEPTH_UNIT,
                "status": LABEL, "notes": " | ".join(self.notes) or "none"}


def _mse_row(saved) -> SimpleNamespace:
    """One stored MSE run as OA reads it (M123): the EFFECTIVE lineage under the record's attribute names."""
    repairs = "; ".join(
        f"{r.field} = {r.value_label}{' (reference since deleted)' if r.unlinked else ''} — repair #{r.id} by "
        f"{r.confirmer} at {r.confirmed_at:%Y-%m-%d %H:%M} UTC; evidence: {r.evidence}" for r in saved.repairs)
    return SimpleNamespace(
        id=saved.id, created_at=saved.created_at, label=saved.label, mse_psi=saved.stored_mse_psi,
        input_snapshot_json=saved.input_snapshot, wellbore_id=saved.effective_wellbore_id,
        report_id=saved.effective_report_id, md_m=saved.effective_md_m, lineage_version=saved.lineage_version,
        input_source=saved.input_source, lineage_class=saved.lineage_class, repairs_text=repairs)


def _num(value, *, allow_negative: bool = False) -> Optional[float]:
    state, number, _reason = ev.classify_number(value, allow_negative=allow_negative)
    return number if state == ev.STATE_VALUE else None


class _Mapped(NamedTuple):
    """The only mapping fields the analysis consumes (``confidence`` is description-dependent and not used)."""
    canonical_id: str
    method: str


def _map(mapper, cache: Dict[tuple, Any], code, description) -> _Mapped:
    """``mapper.map_activity`` memoised (M95: the mapper was ~90 % of a year's analysis).

    A learned or exact code match decides ``canonical_id`` and ``method`` from the code alone (the description
    only nudges ``confidence``), so it is cached per code; otherwise the description decides and the result is
    cached per (code, description).
    """
    by_code = cache.get((code,))
    if by_code is None and code:
        found = mapper.map_activity(code, "")
        by_code = cache[(code,)] = _Mapped(found.canonical_id, found.method)
    if by_code is not None and by_code.method in ("learned", "exact"):
        return by_code
    key = (code, description)
    if key not in cache:
        found = mapper.map_activity(code, description)
        cache[key] = _Mapped(found.canonical_id, found.method)
    return cache[key]


def _scope_label(db, scope) -> str:
    """Well and wellbore by name (ids kept) so a shown or exported result names what it covers."""
    from core.database import Well, Wellbore

    with db.session_scope() as session:
        well = session.get(Well, scope.well_id)
        bore = session.get(Wellbore, scope.wellbore_id) if scope.wellbore_id else None
        label = f"{well.name} (well #{well.id})" if well is not None else f"Well #{scope.well_id} (not found)"
        if scope.wellbore_id:
            label += (f" / {bore.name} (wellbore #{bore.id})" if bore is not None
                      else f" / Wellbore #{scope.wellbore_id} (not found)")
        return label + ("" if scope.wellbore_id else " (whole well)")


def _sum(values: List[Optional[float]]) -> Optional[float]:
    """Sum of known values, or None when any is unknown (an incomplete sum is not a total)."""
    if not values or any(v is None for v in values):
        return None
    return float(sum(values))


def _in_range(day: Optional[date], start: Optional[date], end: Optional[date]) -> bool:
    if day is None:
        return start is None and end is None
    return (start is None or day >= start) and (end is None or day <= end)


def _time(value) -> str:
    return value.strftime("%H:%M") if value is not None else ""


def _check_cancel(cancel_event) -> None:
    """M103: cooperative cancellation between sections (a background job was cancelled or superseded)."""
    if cancel_event is not None and cancel_event.is_set():
        from core.context_jobs import JobCancelled
        raise JobCancelled()


def _rop_basis(footage: Optional[float], hours: Optional[float]) -> str:
    if footage is None:
        return "not assessed: footage unknown"
    if hours is None:
        return "not assessed: hours on bottom unknown"
    if hours == 0:
        return "not assessed: no hours on bottom"
    return "footage / hours on bottom"


def _plan_scope_problem(scope, start, end) -> str:
    """The well plan covers the whole well; any narrower scope makes the comparison incompatible."""
    if scope.wellbore_id:
        return "the plan is recorded per well, not per wellbore"
    if start or end:
        return "the plan covers the whole well; a date range selects only part of the actuals"
    return ""


def _range_text(scope_label: str, start, end) -> str:
    if start is None and end is None:
        return f"{scope_label}; every report date"
    return f"{scope_label}; {start or 'first report'} – {end or 'last report'}"


def _quality(values: List[Optional[float]]) -> Tuple[str, str]:
    """COMPLETE when every value is known, PARTIAL when some are, NOT ASSESSED when none is (or no value)."""
    known = sum(1 for v in values if v is not None)
    if not values:
        return NOT_ASSESSED, "no report in scope"
    if known == len(values):
        return COMPLETE, f"known on {known} of {len(values)} reports"
    if known:
        return PARTIAL, f"unknown on {len(values) - known} of {len(values)} reports; an incomplete sum is not a total"
    return NOT_ASSESSED, f"unknown on every one of {len(values)} reports"


def _kpis(summary, costs, time_summary, footages, drilling_totals, scope_text, scope, cost_reason) -> List[list]:
    """KPI register: every figure with value, unit, scope, source, quality and reason (unknown is never 0)."""
    rows: List[list] = []

    def add(name, value, unit, source, quality, reason, scope_override=None):
        rows.append([name, value, unit, scope_override or scope_text, source, quality, reason])

    n = summary["reports"]
    add("Reports", n, "reports", "daily_reports", COMPLETE if n else NOT_ASSESSED, "" if n else "no report in scope")
    quality, reason = _quality(footages)
    if quality == PARTIAL:
        reason += f"; known sum {summary['footage_known_m']:g} m"
    add("Footage", summary["footage_m"], "m", "daily_reports depth 00:00 → 24:00", quality, reason)
    quality, reason = _quality(drilling_totals)
    add("Drilling time", summary["drilling_hours"], "h", "time_logs_24h mapped to DRILLING", quality, reason)
    pairs = int(summary["weighted_rop_days"].split(" ")[0]) if n else 0
    add("Time-weighted ROP", summary["weighted_rop_m_h"], "m/h", "Σ footage ÷ Σ drilling time (daily)",
        COMPLETE if n and pairs == n else PARTIAL if pairs else NOT_ASSESSED,
        f"{summary['weighted_rop_days']} days have footage and drilling time" if n else "no report in scope")
    unknown = time_summary["unknown_duration_count"]
    log_quality = NOT_ASSESSED if not n or summary["logged_hours"] is None else COMPLETE
    log_reason = f"{unknown} time log(s) without a duration" if unknown else ("" if n else "no report in scope")
    add("Logged time", summary["logged_hours"], "h", "time_logs_24h", log_quality, log_reason)
    add("NPT (time logs)", summary["npt_hours"], "h", "time_logs_24h flagged NPT",
        NOT_ASSESSED if summary["npt_hours"] is None else COMPLETE, log_reason)
    add("NPT share (time logs)", summary["npt_percent"], "%", "NPT time ÷ logged time",
        NOT_ASSESSED if summary["npt_percent"] is None else COMPLETE,
        log_reason or ("" if summary["npt_percent"] is not None else "logged time is zero or unknown"))
    register = summary["npt_register_hours"]
    add("NPT (NPT register)", register, "h", "npt_reports (separate source, never added to time-log NPT)",
        COMPLETE if register is not None else NOT_ASSESSED,
        ("" if register is not None else "no register row in scope, or a row without a duration")
        + ("; only rows linked to this wellbore's reports" if scope.wellbore_id else ""))
    add("Bit runs", summary["bit_runs"], "runs", "drilling_parameters (canonical rows)", COMPLETE, "")
    mse_reason = []
    if summary.get("mse_legacy_lineage"):
        mse_reason.append(f"{summary['mse_legacy_lineage']} saved before lineage was recorded ({LEGACY_LINEAGE})")
    if summary.get("mse_without_wellbore"):
        mse_reason.append(f"{summary['mse_without_wellbore']} without a wellbore not attributed")
    mse_reason.append("dated by save time")
    add("MSE calculations", summary["mse_points"], "calculations", "mse_calculations (stored runs only)",
        PARTIAL if summary.get("mse_legacy_lineage") or summary.get("mse_without_wellbore") else COMPLETE,
        "; ".join(mse_reason))
    if cost_reason:
        add("Actual cost", None, "currency", "cost_records", NOT_ASSESSED, cost_reason)
        return rows
    by_currency: Dict[Optional[str], List[Any]] = {}
    for group in costs["groups"]:
        by_currency.setdefault(group["currency"], []).append(group["actual"])
    for currency, actuals in sorted(by_currency.items(), key=lambda item: item[0] or "~"):
        if currency is None:
            add("Actual cost (currency unknown)", None, "unknown", "cost_records", NOT_ASSESSED,
                "records without a currency are never summed")
            continue
        missing = sum(1 for a in actuals if a is None)
        add(f"Actual cost ({currency})", None if missing else sum(actuals), currency, "cost_records",
            NOT_ASSESSED if missing else COMPLETE,
            f"{missing} categor(y/ies) without an actual amount" if missing else "per currency, never converted")
    if not by_currency:
        add("Actual cost", None, "currency", "cost_records", NOT_ASSESSED, "no cost record in scope")
    return rows


def analyze(db, scope: ev.AnalysisScope, *, start: Optional[date] = None,
            end: Optional[date] = None, cancel_event=None) -> OperationalAnalysis:
    """Compute every table for ``scope``; sessions stay inside, DTOs come out.

    ``cancel_event`` (M103): checked between sections; a set event stops the run with ``JobCancelled``.
    """
    from core.activity_mapper import ActivityMapper
    from core.cost_semantics import summarize_costs
    from core.database import (CostRecord, DailyReport, DrillingParameters, NPTReport,
                               TimeLog24H, Wellbore)
    from core.operational_time import summarize_time_logs
    from core.operations_intelligence import canonical_params_clause

    problem = scope.problem()
    if problem:
        raise ValueError(f"Operational analysis not assessed: {problem}.")
    if start and end and start > end:
        raise ValueError("The start date is after the end date.")
    notes: List[str] = []
    tables: Dict[str, Tuple[Sequence[str], List[list]]] = {}
    drill: Dict[str, List[Optional[int]]] = {}
    mapper = ActivityMapper()
    mapped_cache: Dict[tuple, Any] = {}
    scope_label = _scope_label(db, scope)

    with db.session_scope() as session:
        reports = [r for r in ev.scoped_reports_query(session, scope)
                   .order_by(DailyReport.report_date, DailyReport.report_number, DailyReport.id).all()
                   if _in_range(r.report_date, start, end)]
        report_ids = [r.id for r in reports]
        logs_by_report: Dict[int, list] = {rid: [] for rid in report_ids}
        if report_ids:
            for log in (session.query(TimeLog24H).filter(TimeLog24H.report_id.in_(report_ids))
                        .order_by(TimeLog24H.report_id, TimeLog24H.time_from, TimeLog24H.id)):
                logs_by_report[log.report_id].append(SimpleNamespace(
                    id=log.id, report_id=log.report_id, duration=log.duration, is_npt=log.is_npt,
                    code=(log.main_code or "").strip(), sub_code=(log.sub_code or "").strip(),
                    category=log.npt_category or "", description=log.activity_description or "",
                    time_from=log.time_from, time_to=log.time_to))

        _check_cancel(cancel_event)
        # ---- daily footage / hours / ROP ------------------------------------------------------------
        daily, daily_ids, weighted_pairs = [], [], []
        footages: List[Optional[float]] = []
        drilling_totals: List[Optional[float]] = []
        activity: Dict[str, Dict[str, Any]] = {}
        npt_rows, npt_ids = [], []
        all_logs = []
        for report in reports:
            logs = logs_by_report.get(report.id, [])
            all_logs.extend(logs)
            d0, d1 = _num(report.depth_0000), _num(report.depth_2400)
            reasons = []
            footage = None
            if d0 is None or d1 is None:
                reasons.append("depth 00:00 or 24:00 missing")
            elif d1 < d0:
                reasons.append(f"INVALID footage: depth decreased by {d0 - d1:g} m")
            else:
                footage = d1 - d0
            drilling, npt, logged = [], [], []
            for log in logs:
                duration = _num(log.duration)
                mapped = _map(mapper, mapped_cache, log.code or log.sub_code, log.description)
                if mapped.method == "unresolved":
                    name = "UNRESOLVED"
                elif mapped.method in TRUSTED_MAPPING:
                    name = mapped.canonical_id
                else:
                    name = f"UNCERTAIN: {mapped.canonical_id}"
                bucket = activity.setdefault(name, {"codes": set(), "methods": set(), "hours": [], "npt": [],
                                                    "logs": 0})
                bucket["codes"].add(log.code or log.sub_code or "(blank)")
                bucket["methods"].add(mapped.method)
                bucket["logs"] += 1
                bucket["hours"].append(duration)
                logged.append(duration)
                if log.is_npt is True:
                    npt.append(duration)
                    bucket["npt"].append(duration)
                    npt_rows.append([report.report_date, _time(log.time_from), _time(log.time_to), duration,
                                     log.category or "(none)", log.code, log.description,
                                     f"time_logs_24h #{log.id} / report #{report.report_number}"])
                    npt_ids.append(report.id)
                elif name == DRILLING_ACTIVITY and log.is_npt is False:
                    drilling.append(duration)
            drill_h = _sum(drilling) if drilling else (0.0 if logs and all(_num(x.duration) is not None
                                                                            for x in logs) else None)
            if not logs:
                reasons.append("no time log")
            rop = None
            if footage is not None and drill_h:
                rop = footage / drill_h
                weighted_pairs.append((footage, drill_h))
            elif footage and drill_h == 0:
                reasons.append("footage without logged drilling time")
            elif logs and drill_h is None:
                reasons.append("drilling time unknown (a time log has no duration)")
            footages.append(footage)
            drilling_totals.append(drill_h)
            daily.append([report.report_date, report.report_number, d0, d1, footage, drill_h,
                          _sum(npt) if npt else (0.0 if logs and all(x.is_npt is not None for x in logs) else None),
                          _sum(logged) if logs else None, rop,
                          "; ".join(reasons), f"daily_reports #{report.id}"])
            daily_ids.append(report.id)
        tables["daily"], drill["daily"] = (COLUMNS["daily"], daily), daily_ids

        tables["activities"] = (COLUMNS["activities"], [
            [name, ", ".join(sorted(b["codes"])), ", ".join(sorted(b["methods"])),
             _sum([h for h in b["hours"] if h is not None]) if b["hours"] else None,
             _sum([h for h in b["npt"] if h is not None]) if b["npt"] else 0.0, b["logs"],
             sum(1 for h in b["hours"] if h is None)]
            for name, b in sorted(activity.items())])
        drill["activities"] = [None] * len(tables["activities"][1])

        _check_cancel(cancel_event)
        # ---- NPT register: a second source, listed apart -----------------------------------------
        register = (session.query(NPTReport).filter(NPTReport.well_id == scope.well_id)
                    .order_by(NPTReport.npt_date, NPTReport.start_time, NPTReport.id).all())
        allowed = set(report_ids)
        register_hours: List[Optional[float]] = []
        for row in register:
            if not _in_range(row.npt_date, start, end):
                continue
            if scope.wellbore_id and row.report_id not in allowed:
                continue                         # cannot be attributed to this wellbore
            hours = _num(row.duration_hours)
            register_hours.append(hours)
            npt_rows.append([row.npt_date, _time(row.start_time), _time(row.end_time), hours, row.npt_category,
                             row.npt_code, row.npt_description, f"npt_reports #{row.id}"])
            npt_ids.append(row.report_id if row.report_id in allowed else None)
        order = sorted(range(len(npt_rows)), key=lambda i: (npt_rows[i][0] or date.min, npt_rows[i][1]))
        tables["npt"] = (COLUMNS["npt"], [npt_rows[i] for i in order])
        drill["npt"] = [npt_ids[i] for i in order]

        _check_cancel(cancel_event)
        # ---- bit runs (DrillingParameters; legacy duplicates excluded) ----------------------------
        query = session.query(DrillingParameters).filter(DrillingParameters.well_id == scope.well_id)
        if scope.wellbore_id:
            query = query.filter(DrillingParameters.report_id.in_(report_ids or [-1]))
        else:
            query = query.filter(canonical_params_clause(DrillingParameters))
        runs: Dict[Tuple[str, Any], Dict[str, Any]] = {}
        for p in query.order_by(DrillingParameters.report_date, DrillingParameters.id).all():
            if not _in_range(p.report_date, start, end) or not (p.bit_no or "").strip():
                continue
            run = runs.setdefault(((p.bit_no or "").strip(), p.bit_rerun), {
                "size": p.bit_size, "type": p.bit_type or "", "in": [], "out": [], "drilled": [], "hours": [],
                "reports": [], "rows": [], "details": []})
            run["in"].append(_num(p.depth_in))
            run["out"].append(_num(p.depth_out))
            run["drilled"].append(_num(p.bit_drilled))
            run["hours"].append(_num(p.hours_on_bottom))
            run["reports"].append(p.report_id)
            run["rows"].append(p.id)
            run["details"].append({"date": p.report_date, "report": p.report_id, "row": p.id, "in": _num(p.depth_in),
                                   "out": _num(p.depth_out), "drilled": _num(p.bit_drilled),
                                   "hours": _num(p.hours_on_bottom)})
        bit_rows, bit_ids, detail_rows, detail_ids = [], [], [], []
        number_of = {r.id: r.report_number for r in reports}
        for (bit_no, rerun), run in runs.items():
            depth_in = min((v for v in run["in"] if v is not None), default=None)
            depth_out = max((v for v in run["out"] if v is not None), default=None)
            footage, basis = _sum(run["drilled"]), "sum of daily drilled"
            if footage is None and depth_in is not None and depth_out is not None and depth_out >= depth_in:
                footage, basis = depth_out - depth_in, "depth out - depth in"
            elif footage is None and depth_in is not None and depth_out is not None:
                basis = f"INVALID: depth out {depth_out:g} m is shallower than depth in {depth_in:g} m"
            elif footage is None:
                basis = "not assessed (drilled and depths incomplete)"
            hours = _sum(run["hours"])
            rop = footage / hours if footage is not None and hours else None
            rop_basis = _rop_basis(footage, hours)
            linked = [r for r in run["reports"] if r is not None]
            bit_rows.append([bit_no, rerun, run["size"], run["type"], depth_in, depth_out, footage, hours, rop,
                             basis, len(run["reports"]), rop_basis,
                             "drilling_parameters #" + ", #".join(str(i) for i in run["rows"])])
            bit_ids.append(linked[0] if linked else None)
            for detail in run["details"]:
                d_in, d_out, drilled, d_hours = detail["in"], detail["out"], detail["drilled"], detail["hours"]
                d_notes = []
                if drilled is None:
                    d_notes.append("drilled not recorded")
                if d_in is not None and d_out is not None and d_out < d_in:
                    d_notes.append("INVALID: depth out shallower than depth in")
                d_rop = drilled / d_hours if drilled is not None and d_hours else None
                if drilled is not None and d_rop is None:
                    d_notes.append(_rop_basis(drilled, d_hours))
                detail_rows.append([bit_no, rerun, detail["date"], number_of.get(detail["report"], ""), d_in, d_out,
                                    drilled, d_hours, d_rop, "; ".join(d_notes),
                                    f"drilling_parameters #{detail['row']}"])
                detail_ids.append(detail["report"] if detail["report"] in allowed else None)
        tables["bit_runs"], drill["bit_runs"] = (COLUMNS["bit_runs"], bit_rows), bit_ids
        tables["bit_rows"], drill["bit_rows"] = (COLUMNS["bit_rows"], detail_rows), detail_ids

        _check_cancel(cancel_event)
        # ---- MSE: stored calculations only, time order, no interpolation --------------------------
        # M123 (D6): runs are read with their audited repairs; ``row`` carries the EFFECTIVE lineage (recorded,
        # else repaired, else unknown) and the class (whole-well / wellbore / depth / unscoped legacy).
        mse_rows, mse_ids = [], []
        mse_without_bore = mse_legacy = 0
        mse_classes: Dict[str, int] = {}
        bore_names = {b.id: b.name for b in session.query(Wellbore).filter(Wellbore.well_id == scope.well_id)}
        well_reports = {r.id: r for r in session.query(DailyReport.id, DailyReport.report_number)
                        .filter(DailyReport.well_id == scope.well_id)}
        for row in (_mse_row(saved) for saved in mse_runs_for_well(session, scope.well_id)):
            day = row.created_at.date() if row.created_at else None
            if not _in_range(day, start, end):
                continue
            if scope.wellbore_id and row.wellbore_id != scope.wellbore_id:
                if row.wellbore_id is None:
                    mse_without_bore += 1      # legacy or saved without a wellbore: not attributable
                continue
            if row.lineage_version is None:
                mse_legacy += 1
            base_class = row.lineage_class.split(" (repaired:")[0]
            mse_classes[base_class] = mse_classes.get(base_class, 0) + 1
            params = (row.input_snapshot_json or {}).get("parameters", {}) if isinstance(
                row.input_snapshot_json, dict) else {}
            report = well_reports.get(row.report_id)
            mse_rows.append([row.created_at, row.label or "", _num(row.mse_psi), _num(params.get("wob_lbf")),
                             _num(params.get("rpm")), _num(params.get("torque_ft_lbf")),
                             _num(params.get("rop_ft_hr")), _num(params.get("bit_diameter_in")),
                             (bore_names.get(row.wellbore_id, f"#{row.wellbore_id}") if row.wellbore_id
                              else (LEGACY_LINEAGE if row.lineage_version is None else "not recorded")),
                             (report.report_number if report is not None
                              else (LEGACY_LINEAGE if row.lineage_version is None else "")),
                             row.input_source if row.lineage_version is not None else LEGACY_LINEAGE,
                             f"mse_calculations #{row.id}", row.lineage_class, _num(row.md_m), row.repairs_text])
            mse_ids.append(report.id if report is not None else None)
        tables["mse"], drill["mse"] = (COLUMNS["mse"], mse_rows), mse_ids
        if mse_without_bore:
            notes.append(f"{mse_without_bore} MSE calculation(s) without a recorded wellbore are not attributed to "
                         "this wellbore")
        if mse_classes:
            notes.append("MSE lineage: " + "; ".join(f"{name} {count}" for name, count in sorted(mse_classes.items()))
                         + " (only depth-class runs carry an entered MD; MSE is dated by save time)")

        _check_cancel(cancel_event)
        # ---- cost: per currency, never mixed --------------------------------------------------------
        cost_rows = [SimpleNamespace(currency=c.currency, category=c.category, planned_cost=c.planned_cost,
                                     actual_cost=c.actual_cost)
                     for c in session.query(CostRecord).filter(CostRecord.well_id == scope.well_id).all()
                     if start is None and end is None or (c.cost_date is not None and _in_range(c.cost_date,
                                                                                                start, end))]
    cost_reason = ""
    if scope.wellbore_id:
        cost_rows, cost_reason = [], "cost records carry no wellbore or report link"
        notes.append("costs not assessed for a wellbore: " + cost_reason)
    costs = summarize_costs(cost_rows)
    if cost_reason:
        costs["status"] = "not assessed: " + cost_reason
    tables["cost"] = (COLUMNS["cost"], [[g["currency"] or "UNKNOWN", g["category"], g["planned"], g["actual"],
                                         g["variance"]] for g in costs["groups"]])
    drill["cost"] = [None] * len(tables["cost"][1])
    if (start or end) and not scope.wellbore_id:
        notes.append("costs without a cost date are outside any date range")

    plan_reason = _plan_scope_problem(scope, start, end)
    plan_rows = []
    if plan_reason:
        notes.append("plan vs actual not assessed: " + plan_reason)
        for metric in ("depth", "hours", "rop", "cost"):
            plan_rows.append([metric, PLAN_UNITS[metric], None, None, None, None, NOT_ASSESSED, plan_reason])
    else:
        plan = db.get_actual_vs_plan(scope.well_id)
        whole = (f"whole well, every report; plan #{plan['plan_id']}" if plan.get("plan_id")
                 else "no active well plan")
        for metric in ("depth", "hours", "rop", "cost"):
            item = plan.get(metric) or {}
            unit = (item.get("currency") or "currency unknown") if metric == "cost" else PLAN_UNITS[metric]
            reason = whole if metric != "cost" or item.get("currency") else f"{whole}; {item.get('currency_status')}"
            plan_rows.append([metric, unit, item.get("planned"), item.get("actual"), item.get("delta"),
                              item.get("pct"), item.get("status", ""), reason])
    tables["plan_vs_actual"], drill["plan_vs_actual"] = (COLUMNS["plan_vs_actual"], plan_rows), [None] * 4

    time_summary = summarize_time_logs(all_logs)
    known_pairs = len(weighted_pairs)
    summary = {
        "reports": len(reports),
        "footage_m": _sum(footages) if reports else None,
        "footage_known_m": float(sum(f for f in footages if f is not None)) if reports else None,
        "footage_days": f"{sum(1 for f in footages if f is not None)} of {len(reports)}",
        "drilling_hours": _sum(drilling_totals) if reports else None,
        "weighted_rop_m_h": (sum(f for f, _ in weighted_pairs) / sum(h for _, h in weighted_pairs)
                             if known_pairs else None),
        "weighted_rop_days": f"{known_pairs} of {len(reports)}",
        "logged_hours": time_summary["total_hours"],
        "npt_hours": time_summary["npt_hours"],
        "npt_percent": time_summary["npt_percent"],
        "npt_register_hours": _sum(register_hours) if register_hours else None,
        "cost_status": costs["status"],
        "cost_currency": costs["currency"],
        "cost_actual": costs["total_actual"],
        "cost_planned": costs["total_planned"],
        "bit_runs": len(bit_rows),
        "mse_points": len(mse_rows),
    }
    if time_summary["unknown_duration_count"]:
        notes.append(f"{time_summary['unknown_duration_count']} time log(s) without a duration: totals not assessed")
    summary["mse_legacy_lineage"] = mse_legacy
    summary["mse_without_wellbore"] = mse_without_bore
    tables["kpis"] = (COLUMNS["kpis"], _kpis(summary, costs, time_summary, footages, drilling_totals,
                                             _range_text(scope_label, start, end), scope, cost_reason))
    drill["kpis"] = [None] * len(tables["kpis"][1])
    tables = {key: tables[key] for key in COLUMNS}          # stable order: register first
    return OperationalAnalysis(scope_label, start, end, summary, tables, drill, notes,
                               datetime.now(timezone.utc).isoformat(timespec="seconds"))


def export(result: OperationalAnalysis, path: str) -> List[str]:
    """CSV (one file per table) or XLSX (one sheet per table), metadata and the UNSIGNED label first."""
    if path.lower().endswith(".xlsx"):
        ev.export_tables_xlsx(path, result.tables, result.metadata())
        return [path]
    return ev.export_tables_csv(path, result.tables, result.metadata())
