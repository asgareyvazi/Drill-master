"""
REST API for DrillMaster Intelligence Platform (P2 future)

Implements:
- Well CRUD
- Report CRUD
- Trajectory / Survey calculations
- Hydraulics / ECD calculations
- Operations Intelligence insights
- Professional Export with metadata

Architecture: UI → Application Services → Domain / Engineering Core → Repositories → Database
API uses same service layer, not direct DB manipulation.

Security: Permission enforcement via same PermissionManager
"""

from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)


class DrillMasterAPI:
    """Professional API with explicit contracts."""

    def __init__(self, db_manager):
        self.db = db_manager

    # ==================== Well ====================

    def get_wells(self) -> List[Dict]:
        """Get all wells with hierarchy."""
        try:
            hierarchy = self.db.get_hierarchy()
            wells = []
            for company in hierarchy:
                for project in company.get("projects", []):
                    for well in project.get("wells", []):
                        wells.append(
                            {
                                "id": well["id"],
                                "name": well["name"],
                                "code": well["code"],
                                "project": project["name"],
                                "company": company["name"],
                                "status": well.get("status", ""),
                            }
                        )
            return wells
        except Exception as exc:
            logger.error(f"API get_wells failed: {exc}", exc_info=True)
            return []

    def get_well(self, well_id: int) -> Optional[Dict]:
        return self.db.get_well_by_id(well_id)

    def get_reports(self, well_id: int) -> List[Dict]:
        return self.db.get_daily_reports_by_well(well_id)

    def get_trajectory(self, well_id: int) -> List[Dict]:
        """Get trajectory with deterministic calculation."""
        try:
            from core.database import SurveyPoint

            with self.db.session_scope() as session:
                points = session.query(SurveyPoint).filter(SurveyPoint.well_id == well_id).order_by(SurveyPoint.md).all()
                return [
                    {
                        "md": p.md,
                        "inc": p.inc,
                        "azi": p.azi,
                        "tvd": p.tvd,
                        "north": p.north,
                        "east": p.east,
                        "dls": p.dls,
                    }
                    for p in points
                ]
        except Exception as exc:
            logger.error(f"API get_trajectory failed: {exc}", exc_info=True)
            return []

    def calculate_trajectory(self, surveys: List[Dict]) -> Dict[str, Any]:
        """Calculate trajectory via engineering core."""
        try:
            from core.engineering.core import TrajectoryEngine

            points = TrajectoryEngine.calculate(surveys)
            return {"success": True, "trajectory": [p.__dict__ for p in points]}
        except Exception as exc:
            return {"success": False, "error": str(exc), "type": "MISSING_INPUT" if "MISSING_INPUT" in str(exc) else "ERROR"}

    def get_intelligence(self, well_id: int) -> Dict[str, Any]:
        """Operations Intelligence with evidence."""
        try:
            from core.operations_intelligence import OperationsIntelligenceService

            service = OperationsIntelligenceService(self.db)
            return service.analyze_well(well_id)
        except Exception as exc:
            logger.error(f"API intelligence failed: {exc}", exc_info=True)
            return {"kpis": {}, "insights": [], "error": str(exc)}

    def get_data_quality(self, report_id: int) -> Dict[str, Any]:
        try:
            from core.data_quality import DataQualityService

            service = DataQualityService(self.db)
            return service.summary(report_id)
        except Exception as exc:
            return {"score": 0, "error": str(exc)}

    def export_professional(self, well_id: int, output_path: str, report_id: int = None) -> Dict[str, Any]:
        """Professional export with full metadata."""
        try:
            from core.professional_export import ProfessionalExcelExport, ProfessionalPDFExport

            if output_path.lower().endswith(".xlsx"):
                success = ProfessionalExcelExport(self.db).export(well_id, output_path, report_id=report_id)
            elif output_path.lower().endswith(".pdf"):
                success = ProfessionalPDFExport(self.db).export(well_id, output_path, report_id=report_id)
            else:
                return {"success": False, "error": "Unsupported format, use .xlsx or .pdf"}

            return {"success": success, "path": output_path}
        except Exception as exc:
            return {"success": False, "error": str(exc)}


def create_app(db_manager=None):
    """Create Flask/FastAPI app - placeholder for future.

    For now returns API object, future will return FastAPI app with routes.

    Future routes:
    - GET /api/wells
    - GET /api/wells/{id}
    - GET /api/wells/{id}/reports
    - GET /api/wells/{id}/trajectory
    - POST /api/trajectory/calculate
    - GET /api/wells/{id}/intelligence
    - GET /api/reports/{id}/quality
    - POST /api/export/professional
    - POST /api/import/witsml
    - GET /api/search/historical?q=...
    """
    api = DrillMasterAPI(db_manager)

    # Future: if FastAPI installed, create app
    try:
        from fastapi import FastAPI

        app = FastAPI(title="DrillMaster Intelligence Platform API", version="2.1")

        @app.get("/api/wells")
        def list_wells():
            return api.get_wells()

        @app.get("/api/wells/{well_id}")
        def get_well(well_id: int):
            return api.get_well(well_id) or {"error": "Not found"}

        @app.get("/api/wells/{well_id}/intelligence")
        def get_intelligence(well_id: int):
            return api.get_intelligence(well_id)

        return app

    except ImportError:
        logger.info("FastAPI not installed - returning API object, not HTTP app. Install with pip install fastapi uvicorn")
        return api
