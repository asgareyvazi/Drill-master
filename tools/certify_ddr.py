"""Run the actual shared application import service against a real workbook.

This certifies ONLY extraction/domain/persistence/reload evidence. It does not
claim desktop interaction or rendered-chart certification. Use a fresh output
directory; never points at or resets a user's operational database.

Usage: python tools/certify_ddr.py WORKBOOK --output /path/to/new/evidence
"""
from __future__ import annotations
import argparse
import hashlib
import json
import logging
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.database import (DatabaseManager, DailyReport, TimeLog24H, TimeLogMorning,
    MudReport, DrillingParameters, SurveyPoint, BHAReport, DownholeEquipment,
    FormationReport, ServiceCompanyPOB, BOPComponent, WasteRecord, FuelWaterInventory,
    BulkMaterials, ServiceCompany, SevenDaysLookahead, EquipmentLog, CasingReport,
    CementReport, TimeDepthData, NPTReport, AuditLog, SafetyReport, MaterialRequest)
from core.ddr_import_service import DDRImportService
from core.survey_records import plot_series

MODELS = (DailyReport, TimeLog24H, TimeLogMorning, MudReport, DrillingParameters,
          SurveyPoint, BHAReport, DownholeEquipment, FormationReport, ServiceCompanyPOB,
          BOPComponent, WasteRecord, FuelWaterInventory, BulkMaterials, ServiceCompany,
          SevenDaysLookahead, EquipmentLog, CasingReport, CementReport, TimeDepthData, NPTReport, SafetyReport, MaterialRequest)


def snapshot(db, report_id):
    result = {}
    with db.session_scope() as session:
        for model in MODELS:
            query = session.query(model)
            query = query.filter(model.id == report_id) if model is DailyReport else query.filter(model.report_id == report_id)
            result[model.__name__] = [{column.name: getattr(row, column.name) for column in model.__table__.columns}
                                     for row in query.order_by(model.id).all()]
    return json.loads(json.dumps(result, default=str))


def certify(path, output):
    path, output = Path(path).resolve(), Path(output).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    output.mkdir(parents=True, exist_ok=True)
    db_path = output / "certification.db"
    if db_path.exists():
        raise FileExistsError(f"Refusing to overwrite certification database: {db_path}")
    logging.basicConfig(filename=output / "runtime.log", level=logging.INFO, force=True)
    db = DatabaseManager()
    db.db_path = str(db_path)
    if not db.initialize():
        raise RuntimeError("Test database initialization failed")
    service = DDRImportService(db)
    extraction, payload = service.extract_file(str(path))
    result = service.import_records(payload)
    if not result.get("report_id") or result.get("failed"):
        raise RuntimeError(json.dumps(result, default=str))
    before = snapshot(db, result["report_id"])
    db.close()
    # A genuinely new DatabaseManager and engine, not cached ORM objects.
    reloaded = DatabaseManager()
    reloaded.db_path = str(db_path)
    if not reloaded.initialize():
        raise RuntimeError("Reload failed")
    after = snapshot(reloaded, result["report_id"])
    again = DDRImportService(reloaded, result["well_id"]).import_records(payload)
    after_repeat = snapshot(reloaded, result["report_id"])
    chemicals = json.loads(after["MudReport"][0]["chemicals_json"] or "[]") if after["MudReport"] else []
    source_chemicals = payload.get("bulk_materials", [])
    chemical_matrix = [{"source": s.get("material_name"), "imported": c["product"], "type": c["type"],
                        "source_stock": s.get("on_hand"), "imported_stock": c["stock"], "unit": c["unit"],
                        "result": "MAPPED" if c["type"] else "REVIEW_REQUIRED"}
                       for s, c in zip(source_chemicals, chemicals)]
    with reloaded.session_scope() as session:
        audits = session.query(AuditLog).filter_by(action="ddr_import", entity_id=result["report_id"]).all()
        audit = json.loads(audits[0].details) if audits else {}
    source_comparisons = {
        "report_date": [payload["daily_report"]["report_date"], after["DailyReport"][0]["report_date"]],
        "bha_component_names": [[r["component_name"] for r in payload.get("bha_components", [])],
                                [r["Component Name"] for r in after["BHAReport"][0]["bha_data_json"]]],
        "survey_md": [[r["md"] for r in payload.get("surveys", [])], [r["md"] for r in after["SurveyPoint"]]],
        "survey_inc": [[r.get("inc") for r in payload.get("surveys", [])], [r["inc"] for r in after["SurveyPoint"]]],
        "survey_azi": [[r.get("azi") for r in payload.get("surveys", [])], [r["azi"] for r in after["SurveyPoint"]]],
        "pob_total": [payload.get("logistics", {}).get("pob_total"), sum(r["personnel_count"] for r in after["ServiceCompanyPOB"])],
    }
    evidence = {
        "scope": "Actual shared application service; no Qt stubs; NOT desktop/Windows certification",
        "file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "platform": platform.platform(), "python": platform.python_version(),
        "windows_desktop": "NOT VERIFIED", "ui_refresh": "NOT VERIFIED", "rendered_2d_3d": "NOT VERIFIED",
        "extraction": {"template_version": extraction.template_version, "tables": extraction.tables_detected,
                       "raw_rows": extraction.total_rows_extracted, "rejected_rows": extraction.rejected_rows,
                       "table_details": [{"name": t.name, "sheet": t.sheet, "rows": t.row_count, "rejected": t.rejected_rows,
                                          "rejection_reasons": t.rejection_reasons} for t in extraction.table_results]},
        "canonical_counts": {k: len(v) if isinstance(v, (dict, list)) else None for k, v in payload.items() if k != "metadata"},
        "result": result, "counts": {k: len(v) for k, v in after.items()},
        "reload_equal": before == after, "reimport_equal": after == after_repeat,
        "reimport_result": again, "audit_count": len(audits),
        "raw_ir_preserved": bool(audit.get("source", {}).get("metadata", {}).get("raw_ir")),
        "source_comparisons": source_comparisons, "chemicals": chemical_matrix,
        "plot_series": plot_series(reloaded.load_survey_points(report_id=result["report_id"])),
        "persisted": after,
    }
    reloaded.close()
    (output / "evidence.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({"file": path.name, "status": result["status"], "imported": result["imported"],
                      "failed": result["failed"], "review": result["review"], "reload_equal": before == after,
                      "reimport_equal": after == after_repeat, "output": str(output)}, indent=2))
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    certify(args.workbook, args.output)
