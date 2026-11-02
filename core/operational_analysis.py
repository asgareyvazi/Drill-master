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

OA_VERSION = "M91 operational analysis v1"
DEPTH_UNIT = "m"
LABEL = "UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED"
DRILLING_ACTIVITY = "DRILLING"
TRUSTED_MAPPING = ("exact", "learned", "description")   # fuzzy matches are shown as UNCERTAIN, never drilling time

COLUMNS = {
    "daily": ("Date", "Report #", "Depth 00:00 (m)", "Depth 24:00 (m)", "Footage (m)", "Drilling h", "NPT h",
              "Logged h", "ROP (m/h)", "Notes", "Source"),
    "activities": ("Activity", "Codes", "Mapping", "Hours", "NPT h", "Logs", "Unknown durations"),
    "npt": ("Date", "From", "To", "Hours", "Category", "Code", "Description", "Source"),
    "bit_runs": ("Bit #", "Rerun", "Size (in)", "Type", "Depth in (m)", "Depth out (m)", "Footage (m)",
                 "Hours on bottom", "ROP (m/h)", "Footage basis", "Reports", "Source"),
    "mse": ("Saved at (UTC)", "Label", "MSE (psi)", "WOB (lbf)", "RPM", "Torque (ft·lbf)", "ROP (ft/h)",
            "Bit (in)", "Source"),
    "cost": ("Currency", "Category", "Planned", "Actual", "Variance"),
    "plan_vs_actual": ("Metric", "Planned", "Actual", "Delta", "Delta %", "Status"),
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


def analyze(db, scope: ev.AnalysisScope, *, start: Optional[date] = None,
            end: Optional[date] = None) -> OperationalAnalysis:
    """Compute every table for ``scope``; sessions stay inside, DTOs come out."""
    from core.activity_mapper import ActivityMapper
    from core.cost_semantics import summarize_costs
    from core.database import CostRecord, DailyReport, DrillingParameters, MSECalculationRecord, NPTReport, TimeLog24H
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
                "reports": [], "rows": []})
            run["in"].append(_num(p.depth_in))
            run["out"].append(_num(p.depth_out))
            run["drilled"].append(_num(p.bit_drilled))
            run["hours"].append(_num(p.hours_on_bottom))
            run["reports"].append(p.report_id)
            run["rows"].append(p.id)
        bit_rows, bit_ids = [], []
        for (bit_no, rerun), run in runs.items():
            depth_in = min((v for v in run["in"] if v is not None), default=None)
            depth_out = max((v for v in run["out"] if v is not None), default=None)
            footage, basis = _sum(run["drilled"]), "sum of daily drilled"
            if footage is None and depth_in is not None and depth_out is not None and depth_out >= depth_in:
                footage, basis = depth_out - depth_in, "depth out - depth in"
            elif footage is None:
                basis = "not assessed (drilled and depths incomplete)"
            hours = _sum(run["hours"])
            rop = footage / hours if footage is not None and hours else None
            linked = [r for r in run["reports"] if r is not None]
            bit_rows.append([bit_no, rerun, run["size"], run["type"], depth_in, depth_out, footage, hours, rop,
                             basis, len(run["reports"]),
                             "drilling_parameters #" + ", #".join(str(i) for i in run["rows"])])
            bit_ids.append(linked[0] if linked else None)
        tables["bit_runs"], drill["bit_runs"] = (COLUMNS["bit_runs"], bit_rows), bit_ids

        # ---- MSE: stored calculations only, time order, no interpolation --------------------------
        mse_rows = []
        for row in (session.query(MSECalculationRecord).filter(MSECalculationRecord.well_id == scope.well_id)
                    .order_by(MSECalculationRecord.created_at, MSECalculationRecord.id)):
            day = row.created_at.date() if row.created_at else None
            if not _in_range(day, start, end):
                continue
            params = (row.input_snapshot_json or {}).get("parameters", {}) if isinstance(
                row.input_snapshot_json, dict) else {}
            mse_rows.append([row.created_at, row.label or "", _num(row.mse_psi), _num(params.get("wob_lbf")),
                             _num(params.get("rpm")), _num(params.get("torque_ft_lbf")),
                             _num(params.get("rop_ft_hr")), _num(params.get("bit_diameter_in")),
                             f"mse_calculations #{row.id}"])
        tables["mse"], drill["mse"] = (COLUMNS["mse"], mse_rows), [None] * len(mse_rows)
        if scope.wellbore_id and mse_rows:
            notes.append("MSE calculations are stored per well (no wellbore); shown for the whole well")

        # ---- cost: per currency, never mixed --------------------------------------------------------
        cost_rows = [SimpleNamespace(currency=c.currency, category=c.category, planned_cost=c.planned_cost,
                                     actual_cost=c.actual_cost)
                     for c in session.query(CostRecord).filter(CostRecord.well_id == scope.well_id).all()
                     if start is None and end is None or (c.cost_date is not None and _in_range(c.cost_date,
                                                                                                start, end))]
    costs = summarize_costs(cost_rows)
    tables["cost"] = (COLUMNS["cost"], [[g["currency"] or "UNKNOWN", g["category"], g["planned"], g["actual"],
                                         g["variance"]] for g in costs["groups"]])
    drill["cost"] = [None] * len(tables["cost"][1])
    if start or end:
        notes.append("costs without a cost date are outside any date range")
    if scope.wellbore_id:
        notes.append("costs and plan-vs-actual are whole-well figures")

    plan = db.get_actual_vs_plan(scope.well_id)
    plan_rows = []
    for metric in ("depth", "hours", "rop", "cost"):
        item = plan.get(metric) or {}
        plan_rows.append([metric, item.get("planned"), item.get("actual"), item.get("delta"), item.get("pct"),
                          item.get("status", "")])
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
    return OperationalAnalysis(scope_label, start, end, summary, tables, drill, notes,
                               datetime.now(timezone.utc).isoformat(timespec="seconds"))


def export(result: OperationalAnalysis, path: str) -> List[str]:
    """CSV (one file per table) or XLSX (one sheet per table), metadata and the UNSIGNED label first."""
    if path.lower().endswith(".xlsx"):
        ev.export_tables_xlsx(path, result.tables, result.metadata())
        return [path]
    return ev.export_tables_csv(path, result.tables, result.metadata())
