"""M173: correct a deferred scalar from the persisted review queue - no re-import, validated, atomic, audited."""
from __future__ import annotations

import json
import shutil
import sqlite3
import warnings
from pathlib import Path

import pytest

from core.ddr_continuation import ACCEPTED, DEFERRED_UNRESOLVED, REJECTED
from core.review_scalar_correction import (
    CorrectionRefused, Target, apply_correction, parse_value, preview_correction, reopen_item,
)

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_ddr_golden_a.xlsx"


class _Rec:
    id = 1


def _target(kind, length=None):
    return Target("mud_report", object, _Rec(), "x", kind, length)


# ---- strict value parsing -----------------------------------------------------------------------------------
@pytest.mark.parametrize("raw", [True, False, "nan", "NaN", "inf", "-inf", "1e400", "1e16", "1,000", "12 m",
                                 "", "   ", None, "0x10", "--1"])
def test_numbers_refuse_booleans_non_finite_overflow_separators_and_text(raw):
    with pytest.raises(CorrectionRefused):
        parse_value(raw, "mud_report.fl", _target("number"))


def test_numbers_bounds_percent_and_integer_rules():
    assert parse_value(" 4.5 ", "mud_report.fl", _target("number"))[0] == 4.5
    assert parse_value(".5", "mud_report.fl", _target("number"))[0] == 0.5
    with pytest.raises(CorrectionRefused, match="minimum"):
        parse_value("-1", "mud_report.fl", _target("number"))                 # fluid loss >= 0
    with pytest.raises(CorrectionRefused, match="percentage"):
        parse_value("101", "mud_report.oil_percent", _target("number"))
    with pytest.raises(CorrectionRefused, match="maximum"):
        parse_value("900", "mud_report.flowline_temp", _target("number"))
    assert parse_value("12", "x.y", _target("integer"))[0] == 12
    for raw in ("12.5", "1e3", True):
        with pytest.raises(CorrectionRefused):
            parse_value(raw, "x.y", _target("integer"))


def test_units_convert_or_refuse():
    value, conversion = parse_value("100", "well_info.water_depth", _target("number"), "ft")
    assert value == pytest.approx(30.48) and conversion["factor_applied"] and conversion["canonical_unit"] == "m"
    assert parse_value("100", "well_info.water_depth", _target("number"), "m")[0] == 100.0
    with pytest.raises(CorrectionRefused, match="Cannot convert"):
        parse_value("100", "well_info.water_depth", _target("number"), "kg")
    with pytest.raises(CorrectionRefused, match="no canonical unit"):
        parse_value("100", "mud_report.unknown_field", _target("number"), "m")


def test_text_and_dates():
    assert parse_value(" ok ", "x.y", _target("text", 4))[0] == "ok"
    for raw in (True, "", "   ", None):                 # never "True" or an empty string in a text field
        with pytest.raises(CorrectionRefused):
            parse_value(raw, "x.y", _target("text", 10))
    with pytest.raises(CorrectionRefused, match="longer"):
        parse_value("abcde", "x.y", _target("text", 4))
    assert str(parse_value("2026-10-01", "safety.last_fire_drill", _target("date"))[0]) == "2026-10-01"
    with pytest.raises(CorrectionRefused, match="YYYY-MM-DD"):
        parse_value("01/10/2026", "safety.last_fire_drill", _target("date"))
    with pytest.raises(CorrectionRefused):
        parse_value("12:00", "x.y", _target("time"))


# ---- real import, fresh file-backed database ---------------------------------------------------------------
@pytest.fixture
def imported(tmp_path):
    from PySide6.QtWidgets import QApplication
    from core import ddr_import_pipeline as pipe
    from core.database import DatabaseManager, Project, Well
    from core.ddr_import_service import DDRImportService
    from core.ddr_well_identity import CHOOSE_SELECTED, make_decision
    from core.import_quality import apply_review_decisions
    from core.import_router import route_file
    from dialogs.excel_import_dialog import has_meaningful_canonical_data

    QApplication.instance() or QApplication([])
    source = tmp_path / "golden.xlsx"
    shutil.copyfile(FIXTURE, source)
    service = DDRImportService()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = pipe.prepare_import(str(source), route=route_file, template_matcher=service._auto_match_template,
                                  extract_file=service.extract_file, meaningful=has_meaningful_canonical_data)
    for row in out.import_report["review"]:
        row["decision"] = "DEFER"
    apply_review_decisions(out.extracted, out.import_report["review"])
    db = DatabaseManager()
    db.db_path = str(tmp_path / "m173.db")
    assert db.initialize()
    with db.session_scope() as session:
        project = session.query(Project).first()
        well = Well(name="M173 selected", code="M173", project_id=project.id)
        other = Well(name="M173 other", code="M173O", project_id=project.id)
        session.add_all([well, other])
        session.flush()
        ids = (well.id, other.id)
    target = DDRImportService(db, ids[0])
    out.extracted["metadata"]["well_identity_decision"] = make_decision(
        target.assess_well_identity(out.extracted["well_info"]), CHOOSE_SELECTED, "M173 test")
    result = target.import_records(out.extracted)
    assert result["report_id"] and result["review_queue"]["pending"] == 35, result
    items = {i["target_field"]: i for i in db.get_import_review_items(ids[0]) if i["review_type"] != "continuation"}
    yield db, ids, result["report_id"], items
    db.close()


def _mud(db, report_id, column):
    from core.database import MudReport
    with db.session_scope() as session:
        return getattr(session.query(MudReport).filter_by(report_id=report_id).one(), column)


def _item(db, well, item_id):
    return next(i for i in db.get_import_review_items(well) if i["id"] == item_id)


def test_queue_items_record_their_target_at_creation(imported):
    db, (well, _), report_id, items = imported
    snap = items["mud_report.oil_percent"]["payload"]["target_at_creation"]
    assert snap["correctable"] and snap["model"] == "MudReport" and snap["value"] is None
    assert items["daily_report.mud_lost_downhole"]["payload"]["target_at_creation"]["column"] == "loss_downhole"
    refused = items["daily_report.note_03"]["payload"]["target_at_creation"]
    assert not refused["correctable"] and "no column" in refused["reason"]
    assert "multi-row" in items["bulk_material.blend_cmt"]["payload"]["target_at_creation"]["reason"]


def test_preview_then_confirmed_correction_is_atomic_audited_and_keeps_the_original(imported):
    from core.database import AuditLog
    db, (well, _), report_id, items = imported
    item = items["mud_report.oil_percent"]
    preview = preview_correction(db, item["id"], well, "5")
    assert preview["current_value"] is None and preview["new_value"] == 5.0 and not preview["conflict"]
    assert preview["original_text"] == "5" and preview["canonical_unit"] == "%"
    assert preview["target"]["model"] == "MudReport" and _mud(db, report_id, "oil_percent") is None   # no write
    for kwargs in ({"confirmed": False, "reason": "x"}, {"confirmed": True, "reason": "  "}):
        with pytest.raises(CorrectionRefused):
            apply_correction(db, item["id"], well, "5", token=preview["token"], **kwargs)
    assert _item(db, well, item["id"])["state"] == DEFERRED_UNRESOLVED
    done = apply_correction(db, item["id"], well, "5", reason="value read from the mud sheet", confirmed=True,
                            token=preview["token"])
    assert done["state"] == ACCEPTED and done["old"] is None and done["new"] == 5.0
    assert _mud(db, report_id, "oil_percent") == 5.0
    stored = _item(db, well, item["id"])
    assert stored["original_text"] == "5" and stored["state"] == ACCEPTED and "Corrected" in stored["resolution_note"]
    (entry,) = stored["decision_history"]
    assert entry["action"] == "CORRECTED" and entry["old"] is None and entry["new"] == 5.0 and entry["reason"]
    with db.session_scope() as session:
        audit = session.query(AuditLog).filter_by(action="ddr_review_correction").one()
        assert json.loads(audit.details)["field"] == "mud_report.oil_percent" and audit.entity_id == item["id"]


def test_changed_target_and_stale_preview_are_refused(imported):
    from core.database import MudReport
    db, (well, _), report_id, items = imported
    kcl = items["mud_report.kcl"]
    preview = preview_correction(db, kcl["id"], well, "3")
    with db.session_scope() as session:                        # someone edits the Mud tab meanwhile
        session.query(MudReport).filter_by(report_id=report_id).one().kcl = 2.5
    with pytest.raises(CorrectionRefused, match="NOT SAVED"):
        apply_correction(db, kcl["id"], well, "3", reason="r", confirmed=True, token=preview["token"])
    assert _mud(db, report_id, "kcl") == 2.5 and _item(db, well, kcl["id"])["state"] == DEFERRED_UNRESOLVED
    conflict = preview_correction(db, kcl["id"], well, "3")
    assert conflict["conflict"] and conflict["current_value"] == 2.5 and conflict["expected_value"] is None
    with pytest.raises(CorrectionRefused, match="changed since"):
        apply_correction(db, kcl["id"], well, "3", reason="r", confirmed=True, token=conflict["token"])


def test_foreign_well_unresolvable_targets_and_invalid_values_keep_the_item_open(imported):
    db, (well, other), report_id, items = imported
    oil = items["mud_report.oil_percent"]
    with pytest.raises(CorrectionRefused, match="selected well"):
        preview_correction(db, oil["id"], other, "5")
    for field, message in (("daily_report.note_03", "no column"), ("bulk_material.blend_cmt", "multi-row")):
        with pytest.raises(CorrectionRefused, match=message):
            preview_correction(db, items[field]["id"], well, "x")
    for raw in ("nan", "True", "1,5", "150"):
        with pytest.raises(CorrectionRefused):
            preview_correction(db, oil["id"], well, raw)
    assert all(i["state"] == DEFERRED_UNRESOLVED for i in db.get_import_review_items(well))


def test_repeated_decisions_need_reopen_and_every_decision_is_kept(imported):
    db, (well, _), report_id, items = imported
    oil = items["mud_report.oil_percent"]
    token = preview_correction(db, oil["id"], well, "5")["token"]
    apply_correction(db, oil["id"], well, "5", reason="first", confirmed=True, token=token)
    with pytest.raises(CorrectionRefused, match="already decided"):
        preview_correction(db, oil["id"], well, "6")
    with pytest.raises(CorrectionRefused, match="reason"):
        reopen_item(db, oil["id"], well, "")
    assert reopen_item(db, oil["id"], well, "wrong sample")["state"] == DEFERRED_UNRESOLVED
    assert _mud(db, report_id, "oil_percent") == 5.0                       # reopening does not revert data
    second = preview_correction(db, oil["id"], well, "6")
    assert second["expected_value"] == 5.0 and second["expected_basis"].startswith("the last correction")
    apply_correction(db, oil["id"], well, "6", reason="second sample", confirmed=True, token=second["token"])
    history = _item(db, well, oil["id"])["decision_history"]
    assert [h["action"] for h in history] == ["CORRECTED", "REOPENED", "CORRECTED"]
    assert [(h.get("old"), h.get("new")) for h in history if h["action"] == "CORRECTED"] == [(None, 5.0), (5.0, 6.0)]
    # Ordinary queue decisions are recorded in the history too.
    reject = items["mud_report.mbt"]
    assert db.resolve_import_review_item(reject["id"], well, "REJECT")["state"] == REJECTED
    assert _item(db, well, reject["id"])["decision_history"][0]["action"] == "REJECT"


def test_unit_conversion_on_the_well_record_and_legacy_items_without_snapshot(imported):
    from core.database import ImportReviewItem, Well
    db, (well, _), report_id, items = imported
    depth = items["well_info.water_depth"]
    preview = preview_correction(db, depth["id"], well, "100", "ft")
    assert preview["new_value"] == pytest.approx(30.48) and preview["expected_value"] == preview["current_value"]
    apply_correction(db, depth["id"], well, "100", unit="ft", reason="survey sheet", confirmed=True,
                     token=preview["token"])
    with db.session_scope() as session:
        assert session.get(Well, well).water_depth == pytest.approx(30.48)
        legacy = session.get(ImportReviewItem, items["mud_report.cake_thickness"]["id"])
        payload = json.loads(legacy.payload_json)
        payload.pop("target_at_creation")                    # an item stored before M173
        legacy.payload_json = json.dumps(payload)
    legacy_preview = preview_correction(db, items["mud_report.cake_thickness"]["id"], well, "2")
    assert legacy_preview["expected_value"] is None and "never canonical" in legacy_preview["expected_basis"]


def test_review_workspace_correction_dialog_end_to_end(imported, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from dialogs.import_review_dialog import ImportReviewDialog, ScalarCorrectionDialog
    db, (well, _), report_id, items = imported
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))
    workspace = ImportReviewDialog(db, well)
    item = next(i for i in workspace.items if i["target_field"] == "mud_report.fl")
    assert workspace.correctable(item)
    assert not workspace.correctable(next(i for i in workspace.items if i["review_type"] == "continuation"))
    dialog = ScalarCorrectionDialog(db, well, item, workspace)
    assert not dialog.save_btn.isEnabled() and not dialog.confirm_box.isEnabled()
    dialog.value_edit.setText("6.4")
    dialog.reason_edit.setText("forced")
    dialog.confirm_box.setChecked(True)                       # even forced: no preview -> no Save
    assert not dialog.save_btn.isEnabled() and dialog.save() is None and _mud(db, report_id, "fl") is None
    dialog.reason_edit.clear()
    dialog.value_edit.setText("abc")
    assert dialog.validate() is None and "Not valid" in dialog.preview_label.text()
    dialog.value_edit.setText("6.4")
    assert dialog.validate()["new_value"] == 6.4
    dialog.confirm_box.setChecked(True)
    assert not dialog.save_btn.isEnabled()                    # a reason is still missing
    dialog.reason_edit.setText("API FL from the mud check sheet")
    assert dialog.save_btn.isEnabled()
    dialog.value_edit.setText("6.5")                          # an edit after the preview invalidates it
    assert not dialog.save_btn.isEnabled() and not dialog.confirm_box.isChecked()
    dialog.validate()
    dialog.confirm_box.setChecked(True)
    assert dialog.save()["new"] == 6.5 and _mud(db, report_id, "fl") == 6.5
    workspace.reload()
    assert next(i for i in workspace.items if i["id"] == item["id"])["state"] == ACCEPTED
    assert workspace.reopen(next(i for i in workspace.items if i["id"] == item["id"]), "recheck")["state"] == \
        DEFERRED_UNRESOLVED
    dialog.deleteLater()
    workspace.deleteLater()


def test_an_older_database_gains_the_history_column_without_losing_items(imported, tmp_path):
    from core.database import DatabaseManager
    db, (well, _), report_id, items = imported
    path = db.db_path
    db.close()
    with sqlite3.connect(path) as raw:
        raw.execute("ALTER TABLE import_review_items DROP COLUMN decision_history_json")
        count = raw.execute("SELECT COUNT(*) FROM import_review_items").fetchone()[0]
    reopened = DatabaseManager()
    reopened.db_path = path
    assert reopened.initialize()
    with sqlite3.connect(path) as raw:
        columns = {row[1] for row in raw.execute("PRAGMA table_info(import_review_items)")}
        assert "decision_history_json" in columns
        assert raw.execute("SELECT COUNT(*) FROM import_review_items").fetchone()[0] == count
    assert all(i["decision_history"] == [] for i in reopened.get_import_review_items(well))
    reopened.close()
