"""Operations dashboard read model (M44): Qt-free, read-only, defined KPIs.

Every number shown on the Home dashboard comes from :func:`build_snapshot`
and has a written definition (:data:`KPI_DEFINITIONS`).  Nothing is
simulated: when a value cannot be computed from stored data the KPI carries
``value=None`` and the UI shows "No data".

The function only reads.  It is called either on the UI thread with the
application's manager (in-memory databases) or in a worker with a separate
read-only connection (``core.export_jobs.worker_database``); it never keeps
ORM objects beyond its own session.

Audit records are used only to *count* DDR imports; no audit details, user
names or source file names are returned.

M53 extends the model without changing the M44 contract:

* :class:`DashboardFilter` scopes every figure (company, project, well, rig,
  status group, period).  All KPIs, the portfolio, the alerts and the recent
  activity are computed from the same filtered well set.
* KPIs carry ``source`` (stored tables), ``as_of`` (freshness), ``note`` (why a
  value is unavailable, or the currency/well it refers to) and ``drilldown``.
* Money is never summed across currencies or across records whose currency is
  unknown (``core.cost_semantics.summarize_costs``); cost per metre and the
  allocated NPT cost are single-well figures only and NPT cost is labelled an
  estimate (allocation of stored actual cost by recorded NPT time).
* :func:`build_well_detail` returns the chart series and the trajectory
  preview of one well from stored rows only; a series without data is empty
  and the UI shows it as unavailable, never as zeros.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

PERIODS = (("7d", "Last 7 days", 7), ("30d", "Last 30 days", 30), ("90d", "Last 90 days", 90),
           ("all", "All dates", None))

ACTIVE_STATUSES = {"drilling", "active"}
PLANNING_STATUSES = {"planning", "design"}
COMPLETED_STATUSES = {"completed", "abandoned", "producing"}

WINDOW_DAYS = 7
STALE_AFTER_DAYS = 3

KPI_DEFINITIONS = {
    "wells_total": "Wells in scope (all companies and projects unless a filter is applied).",
    "wells_active": "Wells in scope whose status is Drilling or Active.",
    "wells_planning": "Wells in scope whose status is Planning or Design.",
    "wells_completed": "Wells in scope whose status is Completed, Producing or Abandoned.",
    "reports_total": "Daily drilling reports stored for the wells in scope (all dates).",
    "reports_window": "Daily reports of the wells in scope dated within the selected period "
                      f"(default last {WINDOW_DAYS} days, today included).",
    "latest_report": "Most recent daily report date of the wells in scope.",
    "npt_window": ("Sum of 24-h time-log durations flagged NPT on reports dated within the selected period. "
                   "No data when no time logs exist in that period."),
    "npt_share": ("NPT hours divided by all logged 24-h time-log hours in the same period. "
                  "No data when no hours are logged."),
    "wells_need_review": "Wells in scope with at least one warning or error in the alerts list.",
    "imports_window": ("DDR imports recorded in the audit log within the selected period "
                       "(count only; all wells, the audit log is not well-scoped)."),
    "latest_depth": ("Deepest 24:00 depth on the latest daily report of each well in scope; "
                     "the note names the well. Depth as stored (metres)."),
    "footage_window": ("Metres drilled on reports dated within the selected period: 24:00 depth minus 00:00 depth, "
                       "or minus the previous report's 24:00 depth of the same well and wellbore. "
                       "Reports without both depths, or with a negative difference, are excluded and counted."),
    "rop_window": ("Footage-weighted ROP = sum of footage / sum of on-bottom hours over drilling-parameter rows "
                   "with a complete valid pair (depth in/out, hours > 0) dated within the selected period "
                   "(BitPerformanceEngine.weighted_rop)."),
    "survey_ready": ("Wells in scope whose stored survey composes without review issues (READY), "
                     "out of the wells that have survey stations."),
    "documents_total": "Documents stored in the document library (count only; names are not shown).",
    "cost_actual": ("Sum of stored actual cost records of the wells in scope dated within the selected period "
                    "(undated records only with All dates). Shown only when every record has the same explicit "
                    "currency; mixed or unknown currencies are never summed."),
    "afe_used": ("Actual cost as a percentage of planned (AFE) cost over the same records as Actual cost; "
                 "single explicit currency only; no data when the planned total is zero or unknown."),
    "cost_per_metre": ("Single well only: all stored actual cost of the well divided by its deepest reported "
                       "24:00 depth. Single explicit currency only."),
    "npt_cost": ("ESTIMATE, single well only: all stored actual cost of the well x NPT hours / all logged hours "
                 "(core.cost_semantics.allocate_npt_cost). No rig rate is assumed."),
}

KPI_SOURCES = {
    "wells_total": "wells", "wells_active": "wells.status", "wells_planning": "wells.status",
    "wells_completed": "wells.status", "reports_total": "daily_reports", "reports_window": "daily_reports",
    "latest_report": "daily_reports.report_date", "npt_window": "time_logs_24h", "npt_share": "time_logs_24h",
    "wells_need_review": "derived alerts", "imports_window": "audit_log (ddr_import)",
    "latest_depth": "daily_reports.depth_2400", "footage_window": "daily_reports depths",
    "rop_window": "drilling_parameters", "survey_ready": "survey_points (composed)",
    "documents_total": "documents", "cost_actual": "cost_records", "afe_used": "cost_records",
    "cost_per_metre": "cost_records, daily_reports", "npt_cost": "cost_records, time_logs",
}

KPI_GROUPS = (
    ("Portfolio", ("wells_total", "wells_active", "wells_planning", "wells_completed")),
    ("Reporting", ("reports_total", "reports_window", "latest_report", "imports_window", "documents_total")),
    ("Drilling", ("latest_depth", "footage_window", "rop_window", "survey_ready")),
    ("Time", ("npt_window", "npt_share", "wells_need_review")),
    ("Cost", ("cost_actual", "afe_used", "cost_per_metre", "npt_cost")),
)

NPT_SHARE_ALERT = 20.0          # % of logged time in the period (same threshold as operations intelligence)

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


@dataclass(frozen=True)
class Kpi:
    key: str
    label: str
    value: Optional[object]
    unit: str = ""
    state: str = "ok"            # ok | warning | error | no_data
    definition: str = ""
    source: str = ""
    as_of: Optional[date] = None
    note: str = ""               # why unavailable, or which currency / well the value refers to
    drilldown: Optional[dict] = None   # {"filter": {...}} or a navigation payload


@dataclass(frozen=True)
class DashboardFilter:
    """Scope of the dashboard. ``None`` means "all" for every field."""
    company: Optional[str] = None
    project: Optional[str] = None
    well_id: Optional[int] = None
    rig: Optional[str] = None
    status_group: Optional[str] = None      # active | planning | completed | other
    period_days: Optional[int] = WINDOW_DAYS   # None = all dates

    def window(self, today: date):
        """(start, end) of the period; start is None for all dates."""
        if self.period_days is None:
            return None, today
        return today - timedelta(days=self.period_days - 1), today

    @property
    def period_label(self) -> str:
        return "all dates" if self.period_days is None else f"{self.period_days} d"


@dataclass(frozen=True)
class Attention:
    severity: str                # error | warning | info
    code: str
    well_id: int
    well_name: str
    message: str
    report_id: Optional[int] = None
    section_id: Optional[int] = None
    target: str = "well"         # well | report | trajectory


@dataclass
class WellRow:
    well_id: int
    name: str
    project: str
    company: str
    status: str
    well_type: str
    report_count: int = 0
    latest_report_id: Optional[int] = None
    latest_report_section_id: Optional[int] = None
    latest_report_number: Optional[int] = None
    latest_report_date: Optional[date] = None
    latest_depth: Optional[float] = None
    days_since_report: Optional[int] = None
    survey_stations: int = 0
    survey_md: Optional[float] = None
    survey_tvd: Optional[float] = None
    survey_status: str = "NO_DATA"
    npt_hours_window: Optional[float] = None
    flags: list = field(default_factory=list)
    rig: str = "—"
    target_depth: Optional[float] = None
    max_depth: Optional[float] = None

    @property
    def worst_severity(self) -> Optional[str]:
        if not self.flags:
            return None
        return min((f.severity for f in self.flags), key=SEVERITY_ORDER.__getitem__)


@dataclass
class DashboardSnapshot:
    today: date
    generated_at: datetime
    kpis: dict
    wells: list
    attention: list
    recent_reports: list
    filters: DashboardFilter = field(default_factory=DashboardFilter)
    options: dict = field(default_factory=dict)      # filter choices from ALL wells
    activity: list = field(default_factory=list)     # recent activity, newest first
    npt_by_category: dict = field(default_factory=dict)   # scope, selected period (hours)
    npt_daily: list = field(default_factory=list)          # [(date, npt h, logged h)] scope, period

    @property
    def empty(self) -> bool:
        return not self.wells


def _status_group(status: Optional[str]) -> str:
    text = (status or "").strip().lower()
    if text in ACTIVE_STATUSES:
        return "active"
    if text in PLANNING_STATUSES:
        return "planning"
    if text in COMPLETED_STATUSES:
        return "completed"
    return "other"


def _finite(value) -> Optional[float]:
    import math
    try:
        number = float(value)
    except (TypeError, ValueError):  # silent-ok: a non-numeric stored value is unknown (None), never a number
        return None
    return number if math.isfinite(number) else None


def _report_footage(reports) -> dict:
    """report_id -> metres drilled that day, or None when not measurable.

    ``reports`` are (id, well_id, wellbore_id, date, number, depth_0000,
    depth_2400) ordered by date/number.  The 00:00 depth is preferred; the
    previous report of the same well AND wellbore is the fallback.  A negative
    difference (plug-back, sidetrack, typo) is not footage and stays None.
    """
    previous = {}
    footage = {}
    for report_id, well_id, wellbore_id, _day, _number, start, end in reports:
        end_v, start_v = _finite(end), _finite(start)
        key = (well_id, wellbore_id)
        if start_v is None:
            start_v = previous.get(key)
        value = None
        if end_v is not None and start_v is not None and end_v - start_v >= 0:
            value = end_v - start_v
        footage[report_id] = value
        if end_v is not None:
            previous[key] = end_v
    return footage


def _in_window(day, start, end) -> bool:
    return day is not None and (start is None or day >= start) and day <= end


def build_snapshot(db_manager, today: Optional[date] = None,
                   filters: Optional[DashboardFilter] = None) -> DashboardSnapshot:
    """Read the dashboard model in one short-lived session."""
    from core.cost_semantics import allocate_npt_cost, percent_used, summarize_costs
    from core.database import (AuditLog, Company, CostRecord, DailyReport, Document, DrillingParameters, Project,
                               SurveyPoint, TimeLog24H, Well)
    from core.engineering.engines.bit_performance import BitPerformanceEngine
    from core.operational_time import summarize_time_logs
    from core.operations_intelligence import canonical_params_clause
    from core.well_trajectory import INSUFFICIENT_DATA, NO_DATA, READY, compose_well_trajectory

    today = today or date.today()
    filters = filters or DashboardFilter()
    window_start, window_end = filters.window(today)
    session = db_manager.create_session()
    try:
        all_wells = (session.query(Well.id, Well.name, Well.status, Well.well_type, Project.name, Company.name,
                                   Well.rig_name, Well.target_depth)
                     .outerjoin(Project, Well.project_id == Project.id)
                     .outerjoin(Company, Project.company_id == Company.id)
                     .order_by(Well.name, Well.id).all())
        reports = (session.query(DailyReport.id, DailyReport.well_id, DailyReport.section_id,
                                 DailyReport.report_number, DailyReport.report_date, DailyReport.depth_2400,
                                 DailyReport.status, DailyReport.wellbore_id, DailyReport.depth_0000,
                                 DailyReport.created_at)
                   .order_by(DailyReport.report_date, DailyReport.report_number, DailyReport.id).all())
        surveys = (session.query(SurveyPoint.id, SurveyPoint.well_id, SurveyPoint.report_id, SurveyPoint.md,
                                 SurveyPoint.inc, SurveyPoint.azi).all())
        log_query = (session.query(DailyReport.well_id, TimeLog24H.duration, TimeLog24H.is_npt,
                                   TimeLog24H.npt_category, DailyReport.report_date)
                     .join(DailyReport, TimeLog24H.report_id == DailyReport.id))
        all_logs = log_query.all()
        params_query = (session.query(DrillingParameters)
                        .filter(canonical_params_clause(DrillingParameters)))
        params = [(p.well_id, p.report_date, BitPerformanceEngine.paired_observation(p))
                  for p in params_query.all()]
        costs = [dict(well_id=c.well_id, cost_date=c.cost_date, currency=c.currency, category=c.category,
                      planned_cost=c.planned_cost, actual_cost=c.actual_cost)
                 for c in session.query(CostRecord).all()]

        # Audit timestamps are naive UTC; the window starts at local midnight.
        def local_midnight_utc(day):
            return datetime.combine(day, datetime.min.time()).astimezone(timezone.utc).replace(tzinfo=None)
        imports_query = session.query(AuditLog.id).filter(
            AuditLog.action == "ddr_import",
            AuditLog.timestamp < local_midnight_utc(window_end + timedelta(days=1)))
        if window_start is not None:
            imports_query = imports_query.filter(AuditLog.timestamp >= local_midnight_utc(window_start))
        imports_window = imports_query.count()
        documents = (session.query(Document.id, Document.kind, Document.page_count, Document.imported_at)
                     .order_by(Document.imported_at.desc()).all())
        calc_activity = _calculation_activity(session)
    finally:
        session.close()

    options = {"companies": sorted({w[5] for w in all_wells if w[5]}),
               "projects": sorted({w[4] for w in all_wells if w[4]}),
               "rigs": sorted({w[6] for w in all_wells if w[6]}),
               "wells": [(w[0], w[1] or f"Well {w[0]}") for w in all_wells]}

    rows: dict = {}
    for well_id, name, status, well_type, project, company, rig, target in all_wells:
        if filters.company and company != filters.company:
            continue
        if filters.project and project != filters.project:
            continue
        if filters.rig and rig != filters.rig:
            continue
        if filters.well_id and well_id != filters.well_id:
            continue
        if filters.status_group and _status_group(status) != filters.status_group:
            continue
        rows[well_id] = WellRow(well_id=well_id, name=name or f"Well {well_id}", project=project or "—",
                                company=company or "—", status=status or "Not set", well_type=well_type or "—",
                                rig=rig or "—", target_depth=_finite(target))

    scoped_reports = [r for r in reports if r[1] in rows]
    for report_id, well_id, section_id, number, report_date, depth, *_rest in scoped_reports:
        row = rows[well_id]
        row.report_count += 1
        row.latest_report_id, row.latest_report_section_id = report_id, section_id
        row.latest_report_number, row.latest_report_date, row.latest_depth = number, report_date, depth
        depth_v = _finite(depth)
        if depth_v is not None and (row.max_depth is None or depth_v > row.max_depth):
            row.max_depth = depth_v

    stations_by_well = defaultdict(list)
    for survey_id, well_id, report_id, md, inc, azi in surveys:
        stations_by_well[well_id].append({"id": survey_id, "report_id": report_id, "md": md, "inc": inc, "azi": azi})

    hours = defaultdict(lambda: [0.0, 0.0])        # well -> [npt, logged] in the period
    npt_by_category = defaultdict(float)
    daily = defaultdict(lambda: [0.0, 0.0])
    for well_id, duration, is_npt, category, day in all_logs:
        if well_id not in rows or not _in_window(day, window_start, window_end):
            continue
        duration = _finite(duration)
        if duration is None:
            continue
        hours[well_id][1] += duration
        daily[day][1] += duration
        if is_npt:
            hours[well_id][0] += duration
            daily[day][0] += duration
            npt_by_category[(category or "").strip() or "Uncategorised"] += duration

    footage_by_report = _report_footage(
        [(r[0], r[1], r[7], r[4], r[3], r[8], r[5]) for r in reports])
    window_reports = [r for r in scoped_reports if _in_window(r[4], window_start, window_end)]
    window_footage = [footage_by_report.get(r[0]) for r in window_reports]
    costs_by_well = defaultdict(list)
    for cost in costs:
        costs_by_well[cost["well_id"]].append(cost)

    attention = []
    for row in rows.values():
        group = _status_group(row.status)
        if row.latest_report_date is not None:
            row.days_since_report = (today - row.latest_report_date).days
        if row.well_id in hours:
            row.npt_hours_window = hours[row.well_id][0]
        stations = stations_by_well.get(row.well_id, [])
        row.survey_stations = len(stations)
        trajectory = compose_well_trajectory(stations)
        row.survey_status = trajectory.status
        if trajectory.stations:
            row.survey_md, row.survey_tvd = trajectory.stations[-1].md, trajectory.stations[-1].tvd

        def flag(severity, code, message, target="well", report=False):
            row.flags.append(Attention(severity, code, row.well_id, row.name, message,
                                       report_id=row.latest_report_id if report else None,
                                       section_id=row.latest_report_section_id if report else None,
                                       target=target))

        if row.report_count == 0:
            flag("warning" if group == "active" else "info", "NO_REPORTS",
                 "No daily reports" + (" for an active well" if group == "active" else ""))
        else:
            if group == "active" and row.days_since_report is not None and row.days_since_report > STALE_AFTER_DAYS:
                flag("warning", "STALE_REPORTING",
                     f"Last report {row.days_since_report} days ago (active well)", "report", True)
            if row.latest_depth is None:
                flag("warning", "DEPTH_NOT_REPORTED", "Latest report has no midnight depth", "report", True)
            if row.days_since_report is not None and row.days_since_report < 0:
                flag("warning", "FUTURE_REPORT_DATE", "Latest report is dated in the future", "report", True)
        if stations:
            conflicts = [i for i in trajectory.issues if i.code == "CONFLICTING_DUPLICATE"]
            excluded = trajectory.excluded_rows - sum(len(i.survey_ids) for i in conflicts)
            if conflicts:
                flag("error", "SURVEY_CONFLICT",
                     f"{len(conflicts)} survey depth(s) with conflicting readings", "trajectory")
            if excluded:
                flag("warning", "SURVEY_INCOMPLETE",
                     f"{excluded} survey station(s) missing or invalid angles", "trajectory")
        elif row.report_count and trajectory.status in (NO_DATA, INSUFFICIENT_DATA):
            flag("info", "NO_SURVEY", "Reports exist but no survey stations")
        npt, logged = hours.get(row.well_id, (0.0, 0.0))
        if logged and 100.0 * npt / logged > NPT_SHARE_ALERT:
            flag("warning", "NPT_HIGH",
                 f"NPT {100.0 * npt / logged:.1f}% of logged time ({filters.period_label}), "
                 f"above {NPT_SHARE_ALERT:.0f}%", "npt")
        well_costs = summarize_costs(costs_by_well.get(row.well_id, []))
        if well_costs["status"] == "single-currency":
            used = percent_used(well_costs["total_planned"], well_costs["total_actual"])
            if used is not None and used > 100.0:
                flag("warning", "COST_OVER_AFE",
                     f"Actual cost is {used:.1f}% of planned (AFE) cost ({well_costs['currency']})", "cost")
        elif well_costs["status"] in ("multi-currency", "unknown-currency"):
            flag("info", "COST_CURRENCY",
                 "Cost records use " + ("several currencies" if well_costs["status"] == "multi-currency"
                                        else "an unrecorded currency") + "; totals are not summed", "cost")
        attention.extend(row.flags)

    attention.sort(key=lambda a: (SEVERITY_ORDER[a.severity], a.well_name, a.code))
    # Wells needing attention first (error, warning, info, none), then by name.
    well_list = sorted(rows.values(), key=lambda w: (SEVERITY_ORDER.get(w.worst_severity, 3), w.name.lower()))

    groups = defaultdict(int)
    for row in well_list:
        groups[_status_group(row.status)] += 1
    latest = max((r[4] for r in scoped_reports), default=None)
    npt_total = sum(v[0] for v in hours.values())
    logged_total = sum(v[1] for v in hours.values())
    review = sum(1 for row in well_list if any(f.severity in ("error", "warning") for f in row.flags))
    single = well_list[0] if len(well_list) == 1 else None
    period = filters.period_label

    def kpi(key, label, value, unit="", state=None, note="", drilldown=None, as_of=None):
        if state is None:
            state = "no_data" if value is None else "ok"
        return Kpi(key, label, value, unit, state, KPI_DEFINITIONS[key], KPI_SOURCES[key],
                   as_of if as_of is not None else latest, note, drilldown)

    # Drilling figures
    deepest = max((w for w in well_list if _finite(w.latest_depth) is not None),
                  key=lambda w: float(w.latest_depth), default=None)
    measurable = [f for f in window_footage if f is not None]
    rop_pairs = [pair for well_id, day, pair in params
                 if well_id in rows and pair is not None and _in_window(day, window_start, window_end)]
    rop_value = None
    if rop_pairs and sum(h for _f, h in rop_pairs) > 0:
        rop_value = sum(f for f, _h in rop_pairs) / sum(h for _f, h in rop_pairs)
    with_survey = [w for w in well_list if w.survey_stations]
    ready = sum(1 for w in with_survey if w.survey_status == READY)

    # Cost figures (never across currencies)
    period_costs = [c for c in costs if c["well_id"] in rows and (
        (window_start is None) or (c["cost_date"] is not None and _in_window(c["cost_date"], window_start, window_end)))]
    cost = summarize_costs(period_costs)
    currency_note = {"no-records": "No cost records", "multi-currency": "Multiple currencies — not summed",
                     "unknown-currency": "Currency not recorded — not summed"}
    cost_value = cost["total_actual"] if cost["status"] == "single-currency" else None
    cost_note = cost["currency"] if cost_value is not None else currency_note.get(cost["status"], "No data")
    if cost["status"] == "single-currency" and cost["total_actual"] is None:
        cost_note = "Actual amount missing on a record"
    afe = percent_used(cost["total_planned"], cost["total_actual"]) if cost["status"] == "single-currency" else None
    per_metre = npt_cost = None
    per_metre_unit = npt_cost_unit = ""
    per_metre_note = npt_cost_note = "Select a single well"
    if single is not None:
        well_cost = summarize_costs(costs_by_well.get(single.well_id, []))
        if well_cost["status"] != "single-currency" or well_cost["total_actual"] is None:
            per_metre_note = npt_cost_note = currency_note.get(well_cost["status"], "Actual amount missing")
        else:
            if single.max_depth:
                per_metre = well_cost["total_actual"] / single.max_depth
                per_metre_unit = f"{well_cost['currency']}/m"
                per_metre_note = single.name
            else:
                per_metre_note = "No reported depth"
            metrics = summarize_time_logs(_LogRow(d, n) for w, d, n, _c, _day in all_logs if w == single.well_id)
            npt_cost = allocate_npt_cost(well_cost["total_actual"], metrics["npt_hours"], metrics["total_hours"])
            npt_cost_unit = well_cost["currency"] if npt_cost is not None else ""
            npt_cost_note = (f"Estimate (allocated) · {single.name}" if npt_cost is not None
                             else "Time logs incomplete or missing")
    wells_filter = {"filter": {}}
    kpis = {k.key: k for k in (
        kpi("wells_total", "Wells", len(well_list), drilldown=wells_filter),
        kpi("wells_active", "Active", groups["active"], drilldown={"filter": {"status_group": "active"}}),
        kpi("wells_planning", "Planning", groups["planning"], drilldown={"filter": {"status_group": "planning"}}),
        kpi("wells_completed", "Completed", groups["completed"],
            drilldown={"filter": {"status_group": "completed"}}),
        kpi("reports_total", "Daily reports", len(scoped_reports), drilldown={"tab": "Daily Report"}),
        kpi("reports_window", f"Reports ({period})", len(window_reports), drilldown={"tab": "Daily Report"}),
        kpi("latest_report", "Latest report", latest, drilldown={"recent": True}),
        kpi("npt_window", f"NPT ({period})", npt_total if logged_total else None, "h",
            None if not logged_total else ("warning" if npt_total else "ok"), drilldown={"tab": "Analysis"}),
        kpi("npt_share", f"NPT share ({period})",
            (100.0 * npt_total / logged_total) if logged_total else None, "%",
            None if not logged_total else ("warning" if 100.0 * npt_total / logged_total > NPT_SHARE_ALERT
                                           else "ok"), drilldown={"tab": "Analysis"}),
        kpi("wells_need_review", "Wells needing review", review, state="warning" if review else "ok",
            drilldown={"alerts": True}),
        kpi("imports_window", f"DDR imports ({period})", imports_window, as_of=today),
        kpi("latest_depth", "Deepest current depth", None if deepest is None else float(deepest.latest_depth), "m",
            note="" if deepest is None else deepest.name,
            drilldown=None if deepest is None else {"well": deepest.well_id}),
        kpi("footage_window", f"Footage ({period})", sum(measurable) if measurable else None, "m",
            note=(f"{len(measurable)} of {len(window_reports)} reports measurable" if window_reports
                  else "No reports in period")),
        kpi("rop_window", f"ROP ({period})", rop_value, "m/h",
            note=f"{len(rop_pairs)} valid parameter rows" if rop_pairs else "No valid drilling-parameter rows"),
        kpi("survey_ready", "Survey ready", ready if with_survey else None,
            note=f"of {len(with_survey)} wells with surveys" if with_survey else "No survey stations",
            state=None if not with_survey else ("ok" if ready == len(with_survey) else "warning")),
        kpi("documents_total", "Documents", len(documents), as_of=today),
        kpi("cost_actual", f"Actual cost ({period})", cost_value, cost["currency"] or "",
            state=None if cost_value is not None else ("warning" if cost["status"] in currency_note
                                                       and cost["status"] != "no-records" else "no_data"),
            note=cost_note, drilldown={"tab": "Cost"}),
        kpi("afe_used", "AFE used", afe, "%", state=None if afe is None else ("warning" if afe > 100 else "ok"),
            note=cost["currency"] if afe is not None else cost_note, drilldown={"tab": "Cost"}),
        kpi("cost_per_metre", "Cost per metre", per_metre, per_metre_unit, note=per_metre_note, drilldown={"tab": "Cost"}),
        kpi("npt_cost", "NPT cost (estimate)", npt_cost, npt_cost_unit, note=npt_cost_note, drilldown={"tab": "Cost"}),
    )}

    recent = [
        {"report_id": r[0], "well_id": r[1], "section_id": r[2], "number": r[3], "date": r[4],
         "depth": r[5], "status": r[6] or "—", "well_name": rows[r[1]].name}
        for r in reversed(scoped_reports)
    ][:10]
    activity = [dict(kind="report", when=datetime.combine(r["date"], datetime.min.time()), day=r["date"],
                     text=f"Daily report #{r['number']} · {r['well_name']}", payload=r) for r in recent]
    for doc_id, kind, pages, imported_at in documents[:10]:
        if imported_at is None:
            continue
        pages_text = f", {pages} page(s)" if pages else ""
        activity.append(dict(kind="document", when=imported_at, day=imported_at.date(),
                             text=f"Document imported ({(kind or 'file').upper()}{pages_text})", payload=None))
    for when, label, well_id in calc_activity:
        if well_id in rows and when is not None:
            activity.append(dict(kind="calculation", when=when, day=when.date(),
                                 text=f"{label} saved · {rows[well_id].name}",
                                 payload={"type": "well", "id": well_id}))
    activity.sort(key=lambda a: a["when"], reverse=True)
    return DashboardSnapshot(today=today, generated_at=datetime.now(timezone.utc), kpis=kpis,
                             wells=well_list, attention=attention, recent_reports=recent, filters=filters,
                             options=options, activity=activity[:15],
                             npt_by_category=dict(sorted(npt_by_category.items(), key=lambda kv: -kv[1])),
                             npt_daily=[(day, v[0], v[1]) for day, v in sorted(daily.items())])


@dataclass(frozen=True)
class _LogRow:
    duration: object
    is_npt: object


CALCULATION_TABLES = (
    ("CementCalculationRecord", "Cement calculation"), ("CasingCalculationRecord", "Casing calculation"),
    ("TorqueDragCalculationRecord", "Torque & drag calculation"), ("MSECalculationRecord", "MSE calculation"),
    ("MudVolumeCalculationRecord", "Mud volume calculation"),
    ("WellControlKillSheetCalculationRecord", "Kill sheet calculation"),
)


def _calculation_activity(session, limit: int = 10) -> list:
    """(created_at, type label, well_id) of recently saved calculations; labels are never returned."""
    import core.database as database
    found = []
    for name, label in CALCULATION_TABLES:
        model = getattr(database, name, None)
        if model is None or not hasattr(model, "created_at") or not hasattr(model, "well_id"):
            continue
        for created, well_id in (session.query(model.created_at, model.well_id)
                                 .order_by(model.created_at.desc()).limit(limit).all()):
            found.append((created, label, well_id))
    return found


# ---------------------------------------------------------------- well detail
@dataclass
class WellDetail:
    """Chart series and trajectory preview of one well (stored rows only)."""
    well_id: int
    name: str
    status: str = ""
    company: str = "—"
    project: str = "—"
    rig: str = "—"
    well_type: str = "—"
    target_depth: Optional[float] = None
    depth_time: list = field(default_factory=list)       # [(date, depth m)]
    rop: list = field(default_factory=list)              # [(date, ROP m/h)] drilling parameters avg_rop
    mud_weight: list = field(default_factory=list)       # [(date, MW as stored)]
    mud_weight_unit: str = "pcf"
    # MSE (D6, M123): every saved run of the well, whatever its lineage scope (whole-well trend),
    # dated by SAVE time - not a depth log, and not continuous. ``mse_legacy`` is the subset saved
    # before lineage was recorded ("LEGACY - LINEAGE UNKNOWN"); ``mse_recorded`` the rest.
    mse: list = field(default_factory=list)              # [(saved at, MSE psi)] all saved calculations
    mse_recorded: list = field(default_factory=list)     # [(saved at, MSE psi)] lineage recorded at save
    mse_legacy: list = field(default_factory=list)       # [(saved at, MSE psi)] lineage unknown
    npt_by_category: dict = field(default_factory=dict)  # all dates (hours)
    bit_runs: list = field(default_factory=list)         # [(bit no, footage m, weighted ROP m/h)]
    cost_groups: list = field(default_factory=list)      # [(category, planned, actual)] single currency only
    cost_currency: Optional[str] = None
    cost_status: str = "no-records"
    trajectory_status: str = "NO_DATA"
    trajectory: list = field(default_factory=list)       # [(md, tvd, north, east, vs, dls)]
    closure: Optional[tuple] = None                      # (distance m, azimuth deg)
    ecd_available: bool = False                          # no ECD column is stored (see docs)


def build_well_detail(db_manager, well_id: int) -> Optional[WellDetail]:
    """Series for the selected-well panel and charts. ``None`` if the well does not exist."""
    from core.analysis_evidence import valid_rop_values
    from core.cost_semantics import summarize_costs
    from core.database import (Company, CostRecord, DailyReport, DrillingParameters, MSECalculationRecord,
                               MudReport, Project, SurveyPoint, TimeLog24H, Well)
    from core.engineering.engines.bit_performance import BitPerformanceEngine
    from core.operations_intelligence import canonical_params_clause
    from core.well_trajectory import compose_well_trajectory

    session = db_manager.create_session()
    try:
        head = (session.query(Well.id, Well.name, Well.status, Well.well_type, Project.name, Company.name,
                              Well.rig_name, Well.target_depth)
                .outerjoin(Project, Well.project_id == Project.id)
                .outerjoin(Company, Project.company_id == Company.id)
                .filter(Well.id == well_id).first())
        if head is None:
            return None
        detail = WellDetail(well_id=head[0], name=head[1] or f"Well {head[0]}", status=head[2] or "Not set",
                            well_type=head[3] or "—", project=head[4] or "—", company=head[5] or "—",
                            rig=head[6] or "—", target_depth=_finite(head[7]))
        for day, depth in (session.query(DailyReport.report_date, DailyReport.depth_2400)
                           .filter(DailyReport.well_id == well_id)
                           .order_by(DailyReport.report_date, DailyReport.report_number, DailyReport.id).all()):
            if day is not None and _finite(depth) is not None:
                detail.depth_time.append((day, float(depth)))
        params = (session.query(DrillingParameters).filter(DrillingParameters.well_id == well_id)
                  .filter(canonical_params_clause(DrillingParameters))
                  .order_by(DrillingParameters.report_date, DrillingParameters.id).all())
        runs = defaultdict(list)
        for row in params:
            if row.report_date is not None and valid_rop_values([row.avg_rop]):
                detail.rop.append((row.report_date, float(row.avg_rop)))
            if row.bit_no:
                runs[str(row.bit_no)].append(row)
        for bit, rows in runs.items():
            result = BitPerformanceEngine.weighted_rop(rows)
            if result.values.get("valid_pairs"):
                detail.bit_runs.append((bit, result.values["total_footage"], result.value))
        for day, mw in (session.query(MudReport.report_date, MudReport.mw)
                        .filter(MudReport.well_id == well_id).order_by(MudReport.report_date).all()):
            if day is not None and _finite(mw) is not None:
                detail.mud_weight.append((day, float(mw)))
        for created, mse, lineage_version in (
                session.query(MSECalculationRecord.created_at, MSECalculationRecord.mse_psi,
                              MSECalculationRecord.lineage_version)
                .filter(MSECalculationRecord.well_id == well_id)
                .order_by(MSECalculationRecord.created_at).all()):
            if created is not None and _finite(mse) is not None:
                point = (created, float(mse))
                detail.mse.append(point)
                (detail.mse_recorded if lineage_version is not None else detail.mse_legacy).append(point)
        npt = defaultdict(float)
        for duration, category in (session.query(TimeLog24H.duration, TimeLog24H.npt_category)
                                   .join(DailyReport, TimeLog24H.report_id == DailyReport.id)
                                   .filter(DailyReport.well_id == well_id, TimeLog24H.is_npt.is_(True)).all()):
            if _finite(duration) is not None:
                npt[(category or "").strip() or "Uncategorised"] += float(duration)
        detail.npt_by_category = dict(sorted(npt.items(), key=lambda kv: -kv[1]))
        costs = summarize_costs(session.query(CostRecord).filter(CostRecord.well_id == well_id).all())
        detail.cost_status, detail.cost_currency = costs["status"], costs["currency"]
        if costs["status"] == "single-currency":
            detail.cost_groups = [(g["category"] or "Uncategorised", g["planned"], g["actual"])
                                  for g in costs["groups"]]
        stations = [{"id": sid, "report_id": rid, "md": md, "inc": inc, "azi": azi}
                    for sid, rid, md, inc, azi in session.query(SurveyPoint.id, SurveyPoint.report_id,
                                                                 SurveyPoint.md, SurveyPoint.inc, SurveyPoint.azi)
                    .filter(SurveyPoint.well_id == well_id).all()]
    finally:
        session.close()
    trajectory = compose_well_trajectory(stations)
    detail.trajectory_status = trajectory.status
    detail.trajectory = [(s.md, s.tvd, s.north, s.east, s.vs, s.dls) for s in trajectory.stations]
    if trajectory.closure_distance is not None:
        detail.closure = (trajectory.closure_distance, trajectory.closure_azimuth)
    return detail
