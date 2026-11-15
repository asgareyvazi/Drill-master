"""M227: a read-only data-quality workspace - one list of record-level issues of a well, each pointing at its source.

Contract ``data-quality-workspace-v1``. :func:`collect` only reads (its session is rolled back, never committed) and
returns :class:`Issue` rows; every issue names the stored record it is about (``source_table`` / ``source_id``) and a
navigation target (``target``) the main window resolves to the screen that owns the record:

* ``daily_report`` - a daily report without its end-of-day depth (``depth_2400``) or without a section;
* ``import_review`` - DDR review items still open (DEFERRED_UNRESOLVED / VALIDATION_ERROR), one issue per report;
* ``daily_report`` - a section carried forward from an earlier day and not yet confirmed for this day (M217 CARRIED);
* ``daily_report`` / ``well`` - a survey station with a missing inclination or azimuth (the trajectory engine refuses
  incomplete stations; nothing is guessed).

Nothing is scored, corrected or hidden here: the workspace lists what is missing or unconfirmed, and the operator
fixes it in the owning screen, where the usual guards, audit and permissions apply.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

WORKSPACE_VERSION = "data-quality-workspace-v1"

ERROR, WARNING = "ERROR", "WARNING"
OPEN_REVIEW_STATES = ("DEFERRED_UNRESOLVED", "VALIDATION_ERROR")

CATEGORY_REPORT = "Daily report incomplete"
CATEGORY_REVIEW = "DDR review open"
CATEGORY_CARRIED = "Carried forward, not confirmed"
CATEGORY_SURVEY = "Survey station incomplete"
CATEGORIES = (CATEGORY_REPORT, CATEGORY_REVIEW, CATEGORY_CARRIED, CATEGORY_SURVEY)


@dataclass(frozen=True)
class Issue:
    category: str
    severity: str
    message: str
    source_table: str
    source_id: int
    report_id: Optional[int] = None
    report_label: str = ""
    target: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _report_target(report) -> Dict[str, Any]:
    return {"type": "daily_report", "report_id": report.id, "well_id": report.well_id,
            "section_id": report.section_id}


def _label(report) -> str:
    return f"Report #{report.report_number or '?'} ({report.report_date})"


def collect(db, well_id: int) -> List[Issue]:
    """Every record-level issue of ``well_id`` (read-only; the session is rolled back)."""
    from core import ddr_carry_forward as carry
    from core.database import DailyReport, ImportReviewItem, SurveyPoint

    issues: List[Issue] = []
    session = db.create_session()
    try:
        reports = (session.query(DailyReport).filter(DailyReport.well_id == well_id)
                   .order_by(DailyReport.report_date, DailyReport.id).all())
        by_id = {r.id: r for r in reports}
        for report in reports:
            missing = [name for name, value in (("end-of-day depth (depth_2400)", report.depth_2400),
                                                ("section", report.section_id)) if value is None]
            if missing:
                issues.append(Issue(CATEGORY_REPORT, ERROR, f"Missing {', '.join(missing)}", "daily_reports",
                                    report.id, report.id, _label(report), _report_target(report)))
            states = carry.section_states(session, report.id)
            carried = [entry["label"] for key, entry in states.items()
                       if entry.get("state") == carry.CARRIED and not key.startswith("header.")]
            if carried:
                issues.append(Issue(CATEGORY_CARRIED, WARNING,
                                    f"Carried from an earlier day and not yet confirmed: {', '.join(carried)}",
                                    "daily_reports", report.id, report.id, _label(report), _report_target(report)))
        open_items: Dict[int, List[int]] = {}
        for item in (session.query(ImportReviewItem)
                     .filter(ImportReviewItem.well_id == well_id, ImportReviewItem.state.in_(OPEN_REVIEW_STATES))
                     .order_by(ImportReviewItem.report_id, ImportReviewItem.id)):
            open_items.setdefault(item.report_id, []).append(item.id)
        for report_id, item_ids in open_items.items():
            report = by_id.get(report_id)
            issues.append(Issue(CATEGORY_REVIEW, WARNING, f"{len(item_ids)} DDR review item(s) still open",
                                "import_review_items", item_ids[0], report_id,
                                _label(report) if report else f"Report id {report_id}",
                                {"type": "import_review", "well_id": well_id, "report_id": report_id,
                                 "item_ids": item_ids}))
        for station in (session.query(SurveyPoint)
                        .filter(SurveyPoint.well_id == well_id,
                                (SurveyPoint.inc.is_(None)) | (SurveyPoint.azi.is_(None)))
                        .order_by(SurveyPoint.md, SurveyPoint.id)):
            missing = [name for name, value in (("inclination", station.inc), ("azimuth", station.azi))
                       if value is None]
            report = by_id.get(station.report_id)
            issues.append(Issue(CATEGORY_SURVEY, ERROR, f"Station at MD {station.md:g}: missing {' and '.join(missing)}",
                                "survey_points", station.id, station.report_id,
                                _label(report) if report else "",
                                _report_target(report) if report else {"type": "well", "id": well_id}))
    finally:
        session.rollback()
        session.close()
    return issues


def counts(issues: List[Issue]) -> Dict[str, int]:
    return {category: sum(1 for issue in issues if issue.category == category) for category in CATEGORIES}
