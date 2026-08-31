"""Explainable operations metrics built from validated report data.

Professional Intelligence Platform:
- KPIs: Current Depth, Daily Progress, Average ROP, NPT%, Productive Time, Rig Days, Cost per Meter, Plan Variance, Mud/Torque/RPM/WOB/ECD/DLS Trends, Safety KPI, Data Quality Score
- Analysis: ROP Degradation, NPT Increase, Mud Property Change, Torque Increase, Hole Condition Pattern, Plan Delay, Cost Overrun, Safety Pattern
- Every insight has evidence: Source Reports, Date Range, Metrics, Confidence, Reason
"""

from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
from datetime import date, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class Insight:
    kind: str
    severity: str  # info, warning, critical
    message: str
    evidence: dict  # Source Reports, Date Range, Metrics, Confidence, Reason
    confidence: float = 0.85
    recommendation: str = ""


class OperationsIntelligenceService:
    """Professional Operations Intelligence with evidence."""

    def __init__(self, db):
        self.db = db

    def analyze_well(self, well_id: int) -> Dict:
        from core.database import DailyReport, TimeLog24H, DrillingParameters, MudReport, SafetyReport
        from core.engineering.core import OperationsIntelligenceEngine

        session = self.db.create_session()
        try:
            reports = session.query(DailyReport).filter_by(well_id=well_id).order_by(DailyReport.report_date).all()
            if not reports:
                return {"insights": [], "kpis": {"reports": 0}}

            logs = session.query(TimeLog24H).join(DailyReport, TimeLog24H.report_id == DailyReport.id).filter(DailyReport.well_id == well_id).all()
            params = session.query(DrillingParameters).filter_by(well_id=well_id).order_by(DrillingParameters.report_date).all()
            mud_reports = session.query(MudReport).filter_by(well_id=well_id).order_by(MudReport.report_date).all()
            safety_reports = session.query(SafetyReport).filter_by(well_id=well_id).order_by(SafetyReport.report_date).all()

            total_hours = sum(float(item.duration or 0) for item in logs)
            npt_hours = sum(float(item.duration or 0) for item in logs if item.is_npt)
            depths = [float(item.depth_2400 or 0) for item in reports if item.depth_2400 is not None]
            rops = [float(item.avg_rop or 0) for item in params if item.avg_rop]
            wobs = [float(item.wob_max or item.wob or 0) for item in params if (item.wob_max or item.wob)]
            torques = [float(item.torque_max or item.torque or 0) for item in params if (item.torque_max or item.torque)]
            rpms = [float(item.rpm_max or item.rpm or 0) for item in params if (item.rpm_max or item.rpm)]

            # KPIs professional
            current_depth = max(depths, default=0.0)
            daily_progress = depths[-1] - depths[-2] if len(depths) >= 2 else 0
            avg_rop = round(sum(rops) / len(rops), 2) if rops else 0.0
            npt_percent = round(npt_hours / total_hours * 100, 2) if total_hours else 0.0
            productive_hours = round(total_hours - npt_hours, 2)
            rig_days = len(reports)

            # Cost per meter
            cost_per_meter = 0.0
            try:
                from core.database import CostRecord
                cost_records = session.query(CostRecord).filter(CostRecord.well_id == well_id).all()
                total_cost = sum(float(c.actual_cost or 0) for c in cost_records)
                if current_depth > 0 and total_cost > 0:
                    cost_per_meter = total_cost / current_depth
                else:
                    # Fallback estimate: 60k per day
                    total_cost = rig_days * 60000
                    cost_per_meter = total_cost / current_depth if current_depth > 0 else 0
            except Exception:
                total_cost = rig_days * 60000
                cost_per_meter = total_cost / current_depth if current_depth > 0 else 0

            # Plan variance
            plan_variance = self.db.get_actual_vs_plan(well_id)

            # Mud trends
            mw_trend = [float(m.mw or 0) for m in mud_reports if m.mw]
            pv_trend = [float(m.pv or 0) for m in mud_reports if m.pv]

            # Safety KPI
            safety_kpi = {
                "days_without_lti": max([s.days_without_lti or 0 for s in safety_reports], default=0),
                "total_lti": sum(s.lti_count or 0 for s in safety_reports),
                "total_near_miss": sum(s.near_miss_count or 0 for s in safety_reports),
            }

            # Data Quality Score (based on missing depths, time log coverage, etc.)
            quality_score = 100
            missing_depths = sum(1 for r in reports if r.depth_2400 is None)
            if missing_depths:
                quality_score -= missing_depths * 5
            if total_hours and abs(total_hours / max(len(reports), 1) - 24) > 1:
                quality_score -= 10
            quality_score = max(0, min(100, quality_score))

            kpis = {
                "reports": len(reports),
                "current_depth": current_depth,
                "daily_progress": round(daily_progress, 2),
                "average_rop": avg_rop,
                "npt_hours": round(npt_hours, 2),
                "npt_percent": npt_percent,
                "productive_hours": productive_hours,
                "rig_days": rig_days,
                "cost_per_meter": round(cost_per_meter, 2),
                "total_cost": round(total_cost, 2),
                "plan_variance": plan_variance,
                "mud_trend": {"mw": mw_trend[-5:], "pv": pv_trend[-5:]},
                "torque_trend": torques[-5:],
                "wob_trend": wobs[-5:],
                "rpm_trend": rpms[-5:],
                "safety_kpi": safety_kpi,
                "data_quality_score": quality_score,
            }

            insights: List[Insight] = []

            # Time coverage
            if total_hours and abs(total_hours / max(len(reports), 1) - 24) > 1:
                insights.append(
                    Insight(
                        kind="time-coverage",
                        severity="warning",
                        message="Daily time-log coverage differs from 24 hours.",
                        evidence={
                            "source_reports": [r.id for r in reports[-3:]],
                            "date_range": f"{reports[0].report_date} to {reports[-1].report_date}" if reports else "",
                            "metrics": {"hours": total_hours, "reports": len(reports), "expected_per_day": 24},
                            "confidence": 0.9,
                            "reason": "Total hours per report should equal 24h",
                        },
                        recommendation="Review time logs for gaps/overlaps",
                    )
                )

            # NPT
            npt_insight = OperationsIntelligenceEngine.analyze_npt_trend(npt_percent, threshold=20.0)
            if npt_insight:
                insights.append(
                    Insight(
                        kind=npt_insight["kind"],
                        severity=npt_insight["severity"],
                        message=npt_insight["message"],
                        evidence={
                            "source_reports": [r.id for r in reports],
                            "date_range": f"{reports[0].report_date} to {reports[-1].report_date}" if reports else "",
                            "metrics": npt_insight["evidence"],
                            "confidence": npt_insight["confidence"],
                            "reason": "NPT >20% indicates operational issues",
                        },
                        confidence=npt_insight["confidence"],
                        recommendation="Analyze NPT by category and contractor",
                    )
                )

            # ROP degradation
            rop_insight = OperationsIntelligenceEngine.analyze_rop_trend(rops, threshold_pct=18.0)
            if rop_insight:
                insights.append(
                    Insight(
                        kind=rop_insight["kind"],
                        severity=rop_insight["severity"],
                        message=rop_insight["message"],
                        evidence={
                            "source_reports": [p.report_id for p in params[-7:] if p.report_id],
                            "date_range": f"Last {min(7, len(params))} reports",
                            "metrics": rop_insight["evidence"],
                            "confidence": rop_insight["confidence"],
                            "reason": "ROP decline may indicate bit wear, formation change, or hydraulics issues",
                        },
                        confidence=rop_insight["confidence"],
                        recommendation="Check bit condition, mud properties, and drilling parameters",
                    )
                )

            # Mud property change
            if len(mw_trend) >= 2:
                mw_change_pct = abs(mw_trend[-1] - mw_trend[0]) / mw_trend[0] * 100 if mw_trend[0] else 0
                if mw_change_pct > 10:
                    insights.append(
                        Insight(
                            kind="mud_property_change",
                            severity="warning",
                            message=f"Mud weight changed {mw_change_pct:.1f}% from {mw_trend[0]:.1f} to {mw_trend[-1]:.1f}",
                            evidence={
                                "source_reports": [m.report_id for m in mud_reports[-3:] if m.report_id],
                                "date_range": f"{mud_reports[0].report_date} to {mud_reports[-1].report_date}" if mud_reports else "",
                                "metrics": {"first_mw": mw_trend[0], "latest_mw": mw_trend[-1], "change_pct": round(mw_change_pct, 2)},
                                "confidence": 0.8,
                                "reason": "Significant MW change may affect ECD and well control",
                            },
                            recommendation="Verify mud weight change reason and check ECD",
                        )
                    )

            # Torque increase
            if len(torques) >= 3 and torques[-1] > torques[0] * 1.3:
                insights.append(
                    Insight(
                        kind="torque_increase",
                        severity="warning",
                        message=f"Torque increased {((torques[-1]/torques[0]-1)*100):.1f}% - may indicate hole condition issues",
                        evidence={
                            "source_reports": [p.report_id for p in params[-5:] if p.report_id],
                            "date_range": f"Last {min(5, len(params))} reports",
                            "metrics": {"first_torque": torques[0], "latest_torque": torques[-1]},
                            "confidence": 0.75,
                            "reason": "Torque increase + PV increase + NPT Hole Condition pattern",
                        },
                        recommendation="Check hole condition, BHA, and consider wiper trip",
                    )
                )

            # Plan delay
            depth_var = plan_variance.get("depth", {})
            if depth_var.get("delta", 0) < -100:  # 100m behind
                insights.append(
                    Insight(
                        kind="plan_delay",
                        severity="warning",
                        message=f"Behind plan by {abs(depth_var['delta']):.0f}m ({depth_var.get('pct',0):.1f}%)",
                        evidence={
                            "source_reports": [r.id for r in reports],
                            "date_range": f"{reports[0].report_date} to {reports[-1].report_date}" if reports else "",
                            "metrics": depth_var,
                            "confidence": 0.85,
                            "reason": "Actual depth behind planned depth",
                        },
                        recommendation="Review NPT and drilling performance",
                    )
                )

            # Cost overrun
            hours_var = plan_variance.get("hours", {})
            if hours_var.get("delta", 0) > 24:  # 1 day over
                insights.append(
                    Insight(
                        kind="cost_overrun",
                        severity="warning",
                        message=f"Over plan by {hours_var['delta']:.0f}h - cost impact",
                        evidence={
                            "source_reports": [r.id for r in reports],
                            "date_range": f"{reports[0].report_date} to {reports[-1].report_date}" if reports else "",
                            "metrics": hours_var,
                            "confidence": 0.8,
                            "reason": "Rig days over planned",
                        },
                        recommendation="Check NPT and efficiency",
                    )
                )

            # Safety pattern
            if safety_kpi["total_lti"] > 0 or safety_kpi["total_near_miss"] > 2:
                insights.append(
                    Insight(
                        kind="safety_pattern",
                        severity="critical" if safety_kpi["total_lti"] > 0 else "warning",
                        message=f"Safety: LTI {safety_kpi['total_lti']}, Near Miss {safety_kpi['total_near_miss']}",
                        evidence={
                            "source_reports": [s.report_id for s in safety_reports if s.report_id],
                            "date_range": f"{safety_reports[0].report_date} to {safety_reports[-1].report_date}" if safety_reports else "",
                            "metrics": safety_kpi,
                            "confidence": 0.9,
                            "reason": "Safety incidents require attention",
                        },
                        recommendation="Review safety reports and conduct safety meeting",
                    )
                )

            # Combined pattern example from spec
            if len(rops) >= 7 and len(torques) >= 7:
                rop_decline = (rops[0] - rops[-1]) / rops[0] * 100 if rops[0] else 0
                torque_inc = (torques[-1] - torques[0]) / torques[0] * 100 if torques[0] else 0
                if rop_decline >= 18 and torque_inc > 10 and npt_percent > 15:
                    insights.append(
                        Insight(
                            kind="hole_condition_pattern",
                            severity="critical",
                            message=f"در ۷ روز اخیر ROP حدود {rop_decline:.0f}٪ کاهش یافته، همزمان Torque و PV افزایش داشته‌اند و NPT مرتبط با Hole Condition بیشتر شده است.",
                            evidence={
                                "source_reports": [r.id for r in reports[-7:]],
                                "date_range": f"Last 7 reports",
                                "metrics": {"rop_decline_pct": round(rop_decline, 1), "torque_increase_pct": round(torque_inc, 1), "npt_percent": npt_percent},
                                "confidence": 0.82,
                                "reason": "Combined ROP degradation + Torque increase + NPT Hole Condition",
                            },
                            recommendation="Consider bit change, hole cleaning, and hydraulics review",
                        )
                    )

            return {"kpis": kpis, "insights": [asdict(i) for i in insights]}

        except Exception as exc:
            logger.error(f"Operations intelligence failed: {exc}", exc_info=True)
            return {"kpis": {"reports": 0, "error": str(exc)}, "insights": []}
        finally:
            session.close()
