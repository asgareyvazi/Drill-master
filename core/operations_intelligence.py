"""Explainable operations metrics built from validated report data."""
from dataclasses import dataclass, asdict

@dataclass
class Insight:
    kind: str
    severity: str
    message: str
    evidence: dict

class OperationsIntelligenceService:
    def __init__(self, db):
        self.db = db

    def analyze_well(self, well_id):
        from core.database import DailyReport, TimeLog24H, DrillingParameters
        session = self.db.create_session()
        try:
            reports = session.query(DailyReport).filter_by(well_id=well_id).order_by(DailyReport.report_date).all()
            if not reports:
                return {"insights": [], "kpis": {"reports": 0}}
            logs = session.query(TimeLog24H).join(DailyReport, TimeLog24H.report_id == DailyReport.id).filter(DailyReport.well_id == well_id).all()
            params = session.query(DrillingParameters).filter_by(well_id=well_id).order_by(DrillingParameters.report_date).all()
            total_hours = sum(float(item.duration or 0) for item in logs)
            npt_hours = sum(float(item.duration or 0) for item in logs if item.is_npt)
            depths = [float(item.depth_2400 or 0) for item in reports if item.depth_2400 is not None]
            rops = [float(item.avg_rop or 0) for item in params if item.avg_rop]
            kpis = {"reports": len(reports), "productive_hours": round(total_hours - npt_hours, 2), "npt_hours": round(npt_hours, 2), "npt_percent": round(npt_hours / total_hours * 100, 2) if total_hours else 0.0, "current_depth": max(depths, default=0.0), "average_rop": round(sum(rops) / len(rops), 2) if rops else 0.0}
            insights = []
            if total_hours and abs(total_hours / max(len(reports), 1) - 24) > 1:
                insights.append(Insight("time-coverage", "warning", "Daily time-log coverage differs from 24 hours.", {"hours": total_hours, "reports": len(reports)}))
            if kpis["npt_percent"] >= 20:
                insights.append(Insight("npt", "critical", "NPT exceeds 20% of recorded operational time.", {"npt_percent": kpis["npt_percent"], "npt_hours": npt_hours}))
            if len(rops) >= 2 and rops[-1] < rops[0] * 0.8:
                insights.append(Insight("rop", "warning", "Average ROP has declined by more than 20% from the first recorded value.", {"first": rops[0], "latest": rops[-1]}))
            return {"kpis": kpis, "insights": [asdict(item) for item in insights]}
        finally:
            session.close()
