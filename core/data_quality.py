"""Data quality metrics shared by monitoring and import reports.

Professional Features:
- Data Quality Score: completeness, 24h coverage, unit consistency, validation errors, orphan check
- For Analysis dashboard: Current Depth, Daily Progress, Average ROP, NPT%, Productive Time, Rig Days, Cost per Meter, Plan Variance, Mud/Torque/RPM/WOB/ECD/DLS Trends, Safety KPI, Data Quality Score
- Every metric has evidence and confidence
"""

from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class QualityMetric:
    name: str
    value: Optional[float]   # None when the metric cannot be computed from the data
    status: str              # good, warning, critical, unknown
    detail: str = ""
    confidence: float = 1.0
    evidence: dict = None


class DataQualityService:
    """Compute explainable quality metrics for a well/report context."""

    def __init__(self, db):
        self.db = db

    def for_report(self, report_id: int) -> List[QualityMetric]:
        report = self.db.get_daily_report_by_id(report_id) if report_id else None
        metrics: List[QualityMetric] = []

        # Report completeness
        required = ("well_id", "section_id", "report_date", "depth_2400")
        recommended = ("depth_0000", "depth_0600", "summary", "status")
        present_required = sum(report.get(k) not in (None, "") for k in required) if report else 0
        present_recommended = sum(report.get(k) not in (None, "") for k in recommended) if report else 0

        score_required = round(present_required / len(required) * 100, 1) if report else 0.0
        metrics.append(
            QualityMetric(
                name="Report completeness (required)",
                value=score_required,
                status="good" if score_required >= 100 else "critical",
                detail=f"{present_required}/{len(required)} required fields: {', '.join(required)}",
                confidence=1.0,
                evidence={"present": present_required, "total": len(required), "missing": [k for k in required if not report or report.get(k) in (None, "")]},
            )
        )

        score_recommended = round(present_recommended / len(recommended) * 100, 1) if report else 0.0
        metrics.append(
            QualityMetric(
                name="Report completeness (recommended)",
                value=score_recommended,
                status="good" if score_recommended >= 80 else "warning",
                detail=f"{present_recommended}/{len(recommended)} recommended fields",
            )
        )

        # 24h time coverage with professional validation
        logs = []
        overlap_count = 0
        gap_count = 0
        if report:
            session = self.db.create_session()
            try:
                from core.database import TimeLog24H
                logs = session.query(TimeLog24H).filter_by(report_id=report_id).all()
                # Use professional validator
                from core.import_quality import TimeLogValidator
                log_dicts = [
                    {"time_from": l.time_from, "time_to": l.time_to, "duration": l.duration, "main_code": l.main_code}
                    for l in logs
                ]
                validation_report = TimeLogValidator.validate_logs(log_dicts, sheet=f"Report {report_id}")
                overlap_count = sum(1 for issue in validation_report.issues if "overlap" in issue.message.lower())
                gap_count = sum(1 for issue in validation_report.issues if "gap" in issue.message.lower())
            finally:
                session.close()

        # 24h coverage is a claim about recorded time. An entry with no recorded
        # duration makes the total unknown: the missing hours are neither zero nor
        # a subtotal, so the metric reports "unknown" instead of a fabricated 0 h.
        unrecorded = sum(1 for log in logs if log.duration is None)
        if unrecorded:
            metrics.append(
                QualityMetric(
                    name="24h time coverage",
                    value=None,
                    status="unknown",
                    confidence=0.0,
                    detail=(f"{unrecorded} of {len(logs)} entries have no recorded duration; "
                            f"coverage cannot be computed, overlaps: {overlap_count}, gaps: {gap_count}"),
                    evidence={"total_hours": None, "unrecorded_entries": unrecorded,
                              "recorded_entries": len(logs) - unrecorded, "entries": len(logs),
                              "overlaps": overlap_count, "gaps": gap_count},
                )
            )
        else:
            hours = sum(float(log.duration) for log in logs)   # durations are all recorded
            coverage = min(100.0, hours / 24.0 * 100) if hours else 0.0
            metrics.append(
                QualityMetric(
                    name="24h time coverage",
                    value=round(coverage, 1),
                    status="good" if coverage >= 95 else "warning" if coverage >= 70 else "critical",
                    detail=f"{hours:.2f} hours, {len(logs)} entries, overlaps: {overlap_count}, gaps: {gap_count}",
                    evidence={"total_hours": hours, "entries": len(logs), "overlaps": overlap_count, "gaps": gap_count},
                )
            )

        # Unit consistency
        if report:
            from core.database import MudReport, DrillingParameters
            session = self.db.create_session()
            try:
                mud = session.query(MudReport).filter_by(report_id=report_id).first()
                params = session.query(DrillingParameters).filter_by(report_id=report_id).first()

                unit_score = 100
                unit_issues = []
                if mud and mud.mw and (mud.mw < 5 or mud.mw > 30):  # ppg range 5-30
                    unit_score -= 20
                    unit_issues.append(f"MW {mud.mw} outside typical ppg range")
                if params and params.bit_size and (params.bit_size < 1 or params.bit_size > 50):
                    unit_score -= 20
                    unit_issues.append(f"Bit size {params.bit_size} outside typical inch range")

                metrics.append(
                    QualityMetric(
                        name="Unit consistency",
                        value=unit_score,
                        status="good" if unit_score >= 80 else "warning",
                        detail="; ".join(unit_issues) if unit_issues else "Units within expected ranges",
                    )
                )
            finally:
                session.close()

        # Orphan check
        if report:
            session = self.db.create_session()
            try:
                from sqlalchemy import text

                # Check the stored database, not merely the connection's current
                # FK enforcement setting: older/raw writers may have left rows
                # that violate a constraint before this connection was opened.
                violations = session.execute(text("PRAGMA foreign_key_check")).fetchall()
                violation_details = [
                    {
                        "table": row[0],
                        "rowid": row[1],
                        "parent_table": row[2],
                        "foreign_key_index": row[3],
                    }
                    for row in violations[:100]
                ]
                violation_count = len(violations)
                metrics.append(
                    QualityMetric(
                        name="Orphan data check",
                        value=0.0 if violation_count else 100.0,
                        status="critical" if violation_count else "good",
                        detail=(
                            f"{violation_count} database foreign-key violation(s)"
                            if violation_count
                            else "No database foreign-key violations"
                        ),
                        confidence=1.0,
                        evidence={
                            "scope": "database",
                            "violation_count": violation_count,
                            "violations": violation_details,
                            "truncated": violation_count > len(violation_details),
                        },
                    )
                )
            except Exception as exc:
                logger.exception("Could not check database foreign-key integrity")
                metrics.append(
                    QualityMetric(
                        name="Orphan data check",
                        value=None,
                        status="unknown",
                        confidence=0.0,
                        detail=f"Database foreign-key integrity check failed: {exc}",
                        evidence={"scope": "database", "violation_count": None},
                    )
                )
            finally:
                session.close()

        return metrics

    def for_well(self, well_id: int) -> List[QualityMetric]:
        """Quality for entire well across all reports."""
        from core.database import DailyReport

        session = self.db.create_session()
        try:
            reports = session.query(DailyReport).filter_by(well_id=well_id).all()
            if not reports:
                return [QualityMetric("Well completeness", 0, "critical", "No reports")]

            total_reports = len(reports)
            missing_depths = sum(1 for r in reports if r.depth_2400 is None)
            depth_completeness = round((total_reports - missing_depths) / total_reports * 100, 1) if total_reports else 0

            metrics = [
                QualityMetric(
                    name="Depth completeness",
                    value=depth_completeness,
                    status="good" if depth_completeness >= 90 else "warning",
                    detail=f"{total_reports - missing_depths}/{total_reports} reports have depth_2400",
                )
            ]

            # Average quality across reports
            all_scores = []
            for r in reports[:10]:  # sample 10
                summary = self.summary(r.id)
                all_scores.append(summary.get("score", 0))

            avg_score = round(sum(all_scores) / len(all_scores), 1) if all_scores else 0
            metrics.append(
                QualityMetric(
                    name="Average report quality",
                    value=avg_score,
                    status="good" if avg_score >= 80 else "warning",
                    detail=f"Sample of {len(all_scores)} reports",
                )
            )

            # Scope-attribution coverage: what fraction of this well's reports
            # carry a genuine (non-NULL, provably-owned) wellbore / section
            # scope. NULL/ambiguous/unresolved rows are never counted as
            # covered — this metric describes real data quality, it does not
            # manufacture coverage.
            try:
                from core.scope_attribution import ScopeAttributionService

                cov = ScopeAttributionService(self.db).coverage(well_id)
                wb_pct = cov.get("wellbore_coverage_pct")
                sec_pct = cov.get("section_coverage_pct")
                if wb_pct is not None:
                    metrics.append(
                        QualityMetric(
                            name="Wellbore attribution",
                            value=wb_pct,
                            status="good" if wb_pct >= 90 else "warning" if wb_pct >= 50 else "critical",
                            detail=(
                                f"{wb_pct}% of {cov.get('total_reports')} reports "
                                f"have a resolved wellbore ({dict(cov.get('wellbore', {}))})"
                            ),
                            evidence=cov.get("wellbore"),
                        )
                    )
                if sec_pct is not None:
                    metrics.append(
                        QualityMetric(
                            name="Section attribution",
                            value=sec_pct,
                            status="good" if sec_pct >= 90 else "warning" if sec_pct >= 50 else "critical",
                            detail=(
                                f"{sec_pct}% of {cov.get('total_reports')} reports "
                                f"have a resolved section ({dict(cov.get('section', {}))})"
                            ),
                            evidence=cov.get("section"),
                        )
                    )
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("Scope-attribution coverage failed: %s", exc)

            return metrics
        finally:
            session.close()

    def summary(self, report_id: int) -> Dict[str, Any]:
        metrics = self.for_report(report_id)
        # A metric whose input data is incomplete is excluded from the average and
        # reported as unknown; it is never scored as if it had passed or failed.
        known = [m for m in metrics if m.value is not None]
        unknown = [m.name for m in metrics if m.value is None]
        score = round(sum(m.value for m in known) / len(known), 1) if known else None
        return {
            "score": score,
            "status": ("unknown" if score is None else
                       "good" if score >= 90 else "warning" if score >= 60 else "critical"),
            "unknown_metrics": unknown,
            "confidence": round(len(known) / len(metrics), 3) if metrics else 0.0,
            "metrics": [asdict(m) for m in metrics],
            "evidence": {
                "report_id": report_id,
                "metric_count": len(metrics),
                "known_metric_count": len(known),
                "unknown_metric_count": len(unknown),
                "timestamp": __import__("datetime").datetime.now().isoformat(),
            },
        }

    def dashboard_kpis(self, well_id: int) -> Dict[str, Any]:
        """Professional dashboard KPIs as per spec for Analysis tab."""
        from core.operations_intelligence import OperationsIntelligenceService

        # Get operations intelligence
        ops_service = OperationsIntelligenceService(self.db)
        ops_result = ops_service.analyze_well(well_id)

        kpis = ops_result.get("kpis", {})

        # Add data quality
        quality_metrics = self.for_well(well_id)
        known_quality = [m for m in quality_metrics if m.value is not None]
        avg_quality = round(sum(m.value for m in known_quality) / len(known_quality), 1) if known_quality else None

        kpis.update(
            {
                "data_quality_score": avg_quality,
                "data_quality_metrics": [asdict(m) for m in quality_metrics],
            }
        )

        return kpis
