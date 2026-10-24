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
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

ACTIVE_STATUSES = {"drilling", "active"}
PLANNING_STATUSES = {"planning", "design"}
COMPLETED_STATUSES = {"completed", "abandoned", "producing"}

WINDOW_DAYS = 7
STALE_AFTER_DAYS = 3

KPI_DEFINITIONS = {
    "wells_total": "Wells in the database (all companies and projects).",
    "wells_active": "Wells whose status is Drilling or Active.",
    "wells_planning": "Wells whose status is Planning or Design.",
    "wells_completed": "Wells whose status is Completed, Producing or Abandoned.",
    "reports_total": "Daily drilling reports stored.",
    "reports_window": f"Daily reports dated within the last {WINDOW_DAYS} days (today included).",
    "latest_report": "Most recent daily report date in the database.",
    "npt_window": (f"Sum of 24-h time-log durations flagged NPT on reports dated within the last "
                   f"{WINDOW_DAYS} days. No data when no time logs exist in that window."),
    "npt_share": ("NPT hours divided by all logged 24-h time-log hours in the same window. "
                  "No data when no hours are logged."),
    "wells_need_review": "Wells with at least one warning or error in the attention list.",
    "imports_window": (f"DDR imports recorded in the audit log within the last {WINDOW_DAYS} days "
                       "(count only)."),
}

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


@dataclass(frozen=True)
class Kpi:
    key: str
    label: str
    value: Optional[object]
    unit: str = ""
    state: str = "ok"            # ok | warning | error | no_data
    definition: str = ""


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


def build_snapshot(db_manager, today: Optional[date] = None) -> DashboardSnapshot:
    """Read the dashboard model in one short-lived session."""
    from core.database import AuditLog, Company, DailyReport, Project, SurveyPoint, TimeLog24H, Well
    from core.well_trajectory import INSUFFICIENT_DATA, NO_DATA, compose_well_trajectory

    today = today or date.today()
    window_start = today - timedelta(days=WINDOW_DAYS - 1)
    session = db_manager.create_session()
    try:
        well_rows = (session.query(Well.id, Well.name, Well.status, Well.well_type, Project.name, Company.name)
                     .outerjoin(Project, Well.project_id == Project.id)
                     .outerjoin(Company, Project.company_id == Company.id)
                     .order_by(Well.name, Well.id).all())
        reports = (session.query(DailyReport.id, DailyReport.well_id, DailyReport.section_id,
                                 DailyReport.report_number, DailyReport.report_date, DailyReport.depth_2400,
                                 DailyReport.status)
                   .order_by(DailyReport.report_date, DailyReport.report_number, DailyReport.id).all())
        surveys = (session.query(SurveyPoint.id, SurveyPoint.well_id, SurveyPoint.report_id, SurveyPoint.md,
                                 SurveyPoint.inc, SurveyPoint.azi).all())
        logs = (session.query(DailyReport.well_id, TimeLog24H.duration, TimeLog24H.is_npt)
                .join(DailyReport, TimeLog24H.report_id == DailyReport.id)
                .filter(DailyReport.report_date >= window_start, DailyReport.report_date <= today).all())
        # Audit timestamps are naive UTC; the window starts at local midnight.
        def local_midnight_utc(day):
            return datetime.combine(day, datetime.min.time()).astimezone(timezone.utc).replace(tzinfo=None)
        imports_window = (session.query(AuditLog.id)
                          .filter(AuditLog.action == "ddr_import",
                                  AuditLog.timestamp >= local_midnight_utc(window_start),
                                  AuditLog.timestamp < local_midnight_utc(today + timedelta(days=1))).count())
    finally:
        session.close()

    rows: dict = {}
    for well_id, name, status, well_type, project, company in well_rows:
        rows[well_id] = WellRow(well_id=well_id, name=name or f"Well {well_id}", project=project or "—",
                                company=company or "—", status=status or "Not set", well_type=well_type or "—")

    for report_id, well_id, section_id, number, report_date, depth, _status in reports:
        row = rows.get(well_id)
        if row is None:
            continue
        row.report_count += 1
        row.latest_report_id, row.latest_report_section_id = report_id, section_id
        row.latest_report_number, row.latest_report_date, row.latest_depth = number, report_date, depth

    stations_by_well = defaultdict(list)
    for survey_id, well_id, report_id, md, inc, azi in surveys:
        stations_by_well[well_id].append({"id": survey_id, "report_id": report_id, "md": md, "inc": inc, "azi": azi})

    hours = defaultdict(lambda: [0.0, 0.0])        # well -> [npt, logged]
    for well_id, duration, is_npt in logs:
        if duration is None:
            continue
        hours[well_id][1] += float(duration)
        if is_npt:
            hours[well_id][0] += float(duration)

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
        attention.extend(row.flags)

    attention.sort(key=lambda a: (SEVERITY_ORDER[a.severity], a.well_name, a.code))
    # Wells needing attention first (error, warning, info, none), then by name.
    well_list = sorted(rows.values(), key=lambda w: (SEVERITY_ORDER.get(w.worst_severity, 3), w.name.lower()))

    groups = defaultdict(int)
    for row in well_list:
        groups[_status_group(row.status)] += 1
    reports_window = sum(1 for r in reports if r[1] in rows and window_start <= r[4] <= today)
    latest = max((r[4] for r in reports if r[1] in rows), default=None)
    npt_total = sum(v[0] for v in hours.values())
    logged_total = sum(v[1] for v in hours.values())
    review = sum(1 for row in well_list if any(f.severity in ("error", "warning") for f in row.flags))

    def kpi(key, label, value, unit="", state=None):
        if state is None:
            state = "no_data" if value is None else "ok"
        return Kpi(key, label, value, unit, state, KPI_DEFINITIONS[key])

    kpis = {k.key: k for k in (
        kpi("wells_total", "Wells", len(well_list)),
        kpi("wells_active", "Active", groups["active"]),
        kpi("wells_planning", "Planning", groups["planning"]),
        kpi("wells_completed", "Completed", groups["completed"]),
        kpi("reports_total", "Daily reports", len([r for r in reports if r[1] in rows])),
        kpi("reports_window", f"Reports ({WINDOW_DAYS} d)", reports_window),
        kpi("latest_report", "Latest report", latest),
        kpi("npt_window", f"NPT ({WINDOW_DAYS} d)", npt_total if logged_total else None, "h",
            None if not logged_total else ("warning" if npt_total else "ok")),
        kpi("npt_share", f"NPT share ({WINDOW_DAYS} d)",
            (100.0 * npt_total / logged_total) if logged_total else None, "%"),
        kpi("wells_need_review", "Wells needing review", review, state="warning" if review else "ok"),
        kpi("imports_window", f"DDR imports ({WINDOW_DAYS} d)", imports_window),
    )}

    recent = [
        {"report_id": r[0], "well_id": r[1], "section_id": r[2], "number": r[3], "date": r[4],
         "depth": r[5], "status": r[6] or "—", "well_name": rows[r[1]].name}
        for r in reversed(reports) if r[1] in rows
    ][:10]
    return DashboardSnapshot(today=today, generated_at=datetime.now(timezone.utc), kpis=kpis,
                             wells=well_list, attention=attention, recent_reports=recent)
