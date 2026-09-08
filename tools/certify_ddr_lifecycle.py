"""Real A follow-up: actual services/Save All coordinator, not native Qt clicks.

Uses only fresh, non-operational databases. Includes edits, close/reopen,
calculation, the shared 3D Matplotlib boundary, and a clean source replay.
Usage: python tools/certify_ddr_lifecycle.py WORKBOOK --output NEW_DIRECTORY
"""
from __future__ import annotations
import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.certify_ddr import certify, snapshot, MODELS
from core.database import DatabaseManager, DailyReport, AuditLog
from core.ddr_import_service import DDRImportService
from core.save_outcome import save_all, SaveOutcome, SaveIssue, validation_outcome
from core.validators import MudValidator
from core.survey_records import plot_series


def semantic(value):
    if isinstance(value, list):
        return [semantic(item) for item in value]
    if isinstance(value, dict):
        return {key: semantic(item) for key, item in value.items()
                if key not in {"id", "well_id", "section_id", "report_id", "created_at", "updated_at"}}
    return value


def open_database(path):
    manager = DatabaseManager()
    manager.db_path = str(path)
    if not manager.initialize():
        raise RuntimeError(f"Cannot initialize verification database {path}")
    return manager


def certify_lifecycle(path, output):
    path, output = Path(path).resolve(), Path(output).resolve()
    original = certify(path, output / "import")
    report_id, well_id = original["result"]["report_id"], original["result"]["well_id"]
    db_path = output / "import" / "certification.db"
    db = open_database(db_path)
    records = {}
    with db.session_scope() as session:
        for model in MODELS:
            query = session.query(model)
            query = query.filter(model.id == report_id) if model is DailyReport else query.filter(model.report_id == report_id)
            records[model.__name__] = [{col.name: copy.deepcopy(getattr(row, col.name)) for col in model.__table__.columns}
                                      for row in query.order_by(model.id).all()]
    # Explicit verification edits, not additional source measurements or Golden B.
    mud = records["MudReport"][0]
    mud["summary"] = (mud.get("summary") or "") + "\nLifecycle verification edit"
    chemicals = json.loads(mud["chemicals_json"] or "[]")
    original_chemicals = copy.deepcopy(chemicals)
    chemicals[0]["received"] = 2  # explicit user-style inventory edit, no calculated stock overwrite
    mud["chemicals_json"] = json.dumps(chemicals)
    drilling = records["DrillingParameters"][0]
    drilling["bit_no"] = "Lifecycle verification edit"
    bha = records["BHAReport"][0]
    bha["bha_data_json"][0]["Remarks"] = "Lifecycle verification edit"
    downhole = records["DownholeEquipment"][0]
    downhole["equipment_data_json"][0]["Remarks"] = "Lifecycle verification edit"
    formation = records["FormationReport"][0]
    formation["formations"] = formation["formations_json"]
    formation["formations"][0]["Description"] = "Lifecycle verification edit"
    pob = records["ServiceCompanyPOB"][0]
    pob["remarks"] = "Lifecycle verification edit"
    equipment = records["EquipmentLog"][0]
    equipment["notes"] = "Lifecycle verification edit"
    equipment_rows = [row for row in records["EquipmentLog"] if row["equipment_type"] == equipment["equipment_type"]]
    company = records["ServiceCompany"][0]
    company["description"] = "Lifecycle verification edit"
    plans = records["SevenDaysLookahead"]
    plans[0]["remarks"] = "Lifecycle verification edit"
    safety = db.get_safety_report(well_id, report_id=report_id)  # authoritative typed-child view
    safety["safety_observations"] = "Lifecycle verification edit"
    surveys = db.load_survey_points(report_id=report_id)
    calculation = {}

    def save_mud():
        saved = db.save_mud_report(mud)
        if not saved:
            raise RuntimeError("Mud persistence was not confirmed")
        result = validation_outcome("Mud", MudValidator.validate(mud), saved=1)
        for i, row in enumerate(chemicals, 1):
            if not row["type"]:
                result.issues.append(SaveIssue("Mud chemicals", "Unresolved existing catalogue role", status="REVIEW_REQUIRED", row=i, field="type"))
        return result

    def save_surveys():
        calculation.update(db.save_survey_records(surveys, replace_scope=(well_id, report_id)))
        return SaveOutcome(saved=calculation["accepted"], issues=[SaveIssue("Survey", r["reason"],
                           status=r["status"], field=r["field"], row=r["row"]) for r in calculation["review_items"]])

    outcome = save_all([
        ("Drilling", lambda: db.save_drilling_parameters(drilling)), ("Mud", save_mud),
        ("BHA", lambda: db.save_bha_report(well_id, bha)),
        ("Downhole", lambda: db.save_downhole_equipment(well_id, downhole)),
        ("Formation", lambda: db.save_formation_report(well_id, formation)),
        ("Survey", save_surveys), ("POB", lambda: db.save_service_company_pob(pob)),
        ("Fuel/water", lambda: db.save_fuel_water_inventory(records["FuelWaterInventory"][0])),
        ("Equipment", lambda: db.save_equipment_records(well_id, report_id, equipment["equipment_type"], equipment_rows)),
        ("Service company", lambda: db.save_service_company(company)),
        ("Lookahead", lambda: db.save_lookahead_records(well_id, report_id, plans)),
        ("Safety/BOP/empty waste", lambda: db.save_safety_report(safety)),
    ])
    if outcome.status not in {"SUCCESS", "REVIEW_REQUIRED"}:
        raise AssertionError(outcome.summary())
    edited = snapshot(db, report_id)
    assert edited["MudReport"][0]["mw"] == original["persisted"]["MudReport"][0]["mw"]
    assert edited["MudReport"][0]["kcl"] is None and edited["MudReport"][0]["water_percent"] is None
    saved_chemicals = json.loads(edited["MudReport"][0]["chemicals_json"])
    assert saved_chemicals[0]["received"] == 2
    assert saved_chemicals[0]["stock"] == original_chemicals[0]["stock"]
    assert saved_chemicals[1:] == original_chemicals[1:]
    assert edited["BHAReport"][0]["bha_data_json"][0]["Remarks"] == "Lifecycle verification edit"
    assert edited["DownholeEquipment"][0]["equipment_data_json"][0]["Remarks"] == "Lifecycle verification edit"
    assert edited["FormationReport"][0]["formations_json"][0]["Description"] == "Lifecycle verification edit"
    assert edited["ServiceCompanyPOB"][0]["date_in"] == original["persisted"]["ServiceCompanyPOB"][0]["date_in"]
    assert len(edited["SevenDaysLookahead"]) == len(plans) == 11
    assert [p["plan_date"] for p in edited["SevenDaysLookahead"]] == [p["plan_date"] for p in original["persisted"]["SevenDaysLookahead"]]
    assert len(edited["BOPComponent"]) == 5 and edited["WasteRecord"] == []
    db.close()
    reopened = open_database(db_path)
    after_reopen = snapshot(reopened, report_id)
    assert after_reopen == edited
    loaded_surveys = reopened.load_survey_points(report_id=report_id)
    chart_inputs = plot_series(loaded_surveys)
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    from core.trajectory_plot import draw_trajectory_3d
    figure = Figure()
    chart_result = draw_trajectory_3d(figure.add_subplot(111, projection="3d"), loaded_surveys)
    figure.savefig(output / "golden-a-3d-state.png")
    assert chart_result["status"] == "INSUFFICIENT_DATA" and not chart_inputs["md"]
    with reopened.session_scope() as session:
        audits = [{"action": a.action, "details": json.loads(a.details)} for a in session.query(AuditLog)
                  .filter(AuditLog.entity_id == report_id, AuditLog.action.in_(["survey_edit", "lookahead_edit", "equipment_edit"]))]
    reopened.close()
    clean = open_database(output / "clean-replay.db")
    service = DDRImportService(clean)
    _, payload = service.extract_file(str(path))
    replay = service.import_records(payload)
    replay_snapshot = snapshot(clean, replay["report_id"])
    assert replay["failed"] == 0
    assert semantic(replay_snapshot) == semantic(original["persisted"])
    clean.close()
    evidence = {
        "scope": "Actual shared Save All coordinator + database callbacks; service-prepared edits; NOT native widgets",
        "golden_a_sha256": original["sha256"], "golden_b": "NOT AVAILABLE / NOT VERIFIED",
        "import_evidence": "import/evidence.json", "save_all": outcome.to_dict(),
        "edited_counts": {name: len(rows) for name, rows in edited.items()},
        "edit_reload_equal": after_reopen == edited, "clean_source_replay_equal": True,
        "comparison_excludes": "Only generated IDs/context IDs/created_at/updated_at, not source measurements",
        "survey_calculation": calculation, "chart_inputs_2d_3d": chart_inputs,
        "rendered_3d_agg": chart_result, "rendered_native_2d_3d": "NOT VERIFIED",
        "audit_actions": [a["action"] for a in audits], "native_save_all_clicks": "NOT VERIFIED",
        "windows_python312": "NOT VERIFIED", "persisted_after_edit": edited,
    }
    (output / "lifecycle.json").write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: evidence[k] for k in ("scope", "edit_reload_equal", "clean_source_replay_equal", "edited_counts")}, indent=2))
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    certify_lifecycle(args.workbook, args.output)
