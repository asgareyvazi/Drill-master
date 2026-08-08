"""Data quality metrics shared by monitoring and import reports."""
from dataclasses import dataclass


@dataclass
class QualityMetric:
    name: str
    value: float
    status: str
    detail: str = ""


class DataQualityService:
    """Compute explainable quality metrics for a well/report context."""
    def __init__(self, db):
        self.db = db

    def for_report(self, report_id):
        report = self.db.get_daily_report_by_id(report_id) if report_id else None
        metrics = []
        required = ("well_id", "section_id", "report_date", "depth_0000", "depth_2400")
        present = sum(report.get(k) not in (None, "") for k in required) if report else 0
        score = round(present / len(required) * 100, 1) if report else 0.0
        metrics.append(QualityMetric("Report completeness", score, "good" if score >= 90 else "warning" if score >= 60 else "critical", f"{present}/{len(required)} required fields"))
        logs = []
        if report:
            session = self.db.create_session()
            try:
                from core.database import TimeLog24H
                logs = session.query(TimeLog24H).filter_by(report_id=report_id).all()
            finally:
                session.close()
        hours = sum(float(log.duration or 0) for log in logs)
        coverage = min(100.0, hours / 24.0 * 100) if hours else 0.0
        metrics.append(QualityMetric("24h time coverage", round(coverage, 1), "good" if coverage >= 95 else "warning" if coverage >= 70 else "critical", f"{hours:.2f} hours"))
        return metrics

    def summary(self, report_id):
        metrics = self.for_report(report_id)
        score = round(sum(m.value for m in metrics) / len(metrics), 1) if metrics else 0.0
        return {"score": score, "status": "good" if score >= 90 else "warning" if score >= 60 else "critical", "metrics": [m.__dict__ for m in metrics]}
