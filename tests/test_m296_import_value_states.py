"""M296: value states of the numeric DDR header fields in the Excel import (real route, SYNTHETIC workbook).

The synthetic golden workbook (tests/fixtures/synthetic_ddr_golden_a.xlsx) is copied and edited cell by cell
(DDR Remark R9 = depth 00:00, R10 = depth 24:00, J14 = MW pcf), then prepared, reviewed and imported through the
production pipeline into a fresh file-backed database. Expected contract (``core.ddr_import_value_states``):
zero and numbers are stored with an implicit state; blank stays None without an event; an explicit token (N/A, ?)
becomes a recorded state in the import transaction; an ambiguous value (comma, unit suffix) is not stored and
becomes a deferred review item that the strict M173 correction resolves; an existing state is never superseded;
a contradiction is reported, never repaired; any failure, including the audit, rolls everything back.
"""
from __future__ import annotations

import warnings

import pytest

from core import ddr_import_value_states as ivs
from core import ddr_value_states as vs

FIXTURE = "tests/fixtures/synthetic_ddr_golden_a.xlsx"


def _prepared(tmp_path, cells, accept=()):
    import openpyxl

    from core import ddr_import_pipeline as pipe
    from core.ddr_import_service import DDRImportService
    from core.import_quality import apply_review_decisions
    from core.import_router import route_file
    from dialogs.excel_import_dialog import has_meaningful_canonical_data

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")                     # openpyxl: data-validation extension dropped on save
        book = openpyxl.load_workbook(FIXTURE)
        for cell, value in cells.items():
            book["DDR Remark"][cell] = value
        source = tmp_path / f"m296_{len(list(tmp_path.glob('*.xlsx')))}.xlsx"
        book.save(source)
        service = DDRImportService()
        out = pipe.prepare_import(str(source), route=route_file, template_matcher=service._auto_match_template,
                                  extract_file=service.extract_file, meaningful=has_meaningful_canonical_data)
    for row in out.import_report["review"]:
        row["decision"] = "ACCEPT" if row.get("target_field") in accept else "DEFER"
    apply_review_decisions(out.extracted, out.import_report["review"])
    return out.extracted


@pytest.fixture
def target(tmp_path):
    from PySide6.QtWidgets import QApplication

    from core.database import DatabaseManager, Project, Well

    QApplication.instance() or QApplication([])
    db = DatabaseManager()
    db.db_path = str(tmp_path / "m296.db")
    assert db.initialize()
    with db.session_scope() as session:
        well = Well(name="M296 selected", code="M296", project_id=session.query(Project).first().id)
        session.add(well)
        session.flush()
        well_id = well.id
    yield db, well_id
    db.close()


def _import(db, well_id, extracted):
    from core.ddr_import_service import DDRImportService
    from core.ddr_well_identity import CHOOSE_SELECTED, make_decision

    service = DDRImportService(db, well_id)
    extracted["metadata"]["well_identity_decision"] = make_decision(
        service.assess_well_identity(extracted["well_info"]), CHOOSE_SELECTED, "M296 test")
    return service.import_records(extracted)


def _counts(db):
    from core.database import AuditLog, DailyReport, DdrValueState

    with db.session_scope() as session:
        return (session.query(DailyReport).count(), session.query(DdrValueState).count(),
                session.query(AuditLog).filter(AuditLog.action == ivs.AUDIT_ACTION).count())


# ---- classification (pure) ----------------------------------------------------------------------------------
@pytest.mark.parametrize("raw, outcome, state", [
    (None, ivs.BLANK, vs.NOT_REPORTED), ("", ivs.BLANK, vs.NOT_REPORTED), ("  ", ivs.BLANK, vs.NOT_REPORTED),
    (0, ivs.NUMBER, vs.ZERO), (0.0, ivs.NUMBER, vs.ZERO), ("0", ivs.NUMBER, vs.ZERO), (155, ivs.NUMBER, vs.REPORTED),
    ("312.5", ivs.NUMBER, vs.REPORTED), ("N/A", ivs.TOKEN, vs.NOT_APPLICABLE), ("?", ivs.TOKEN, vs.UNKNOWN),
    ("unknown", ivs.TOKEN, vs.UNKNOWN), ("NR", ivs.TOKEN, vs.NOT_REPORTED), ("1,5", ivs.AMBIGUOUS, None),
    ("1,500", ivs.AMBIGUOUS, None), ("12.5 ppg", ivs.AMBIGUOUS, None), ("12 m", ivs.AMBIGUOUS, None),
    ("nan", ivs.AMBIGUOUS, None), (float("nan"), ivs.AMBIGUOUS, None), (float("inf"), ivs.AMBIGUOUS, None),
    (True, ivs.AMBIGUOUS, None),
])
def test_classification(raw, outcome, state):
    result = ivs.classify(raw)
    assert (result["outcome"], result["state"]) == (outcome, state)
    assert (result["value"] is None) == (outcome != ivs.NUMBER)
    assert bool(result["reason"]) == (outcome == ivs.AMBIGUOUS)


def test_a_source_number_never_replaces_a_normalized_value():
    # The extractor may have converted units; a numeric source text only confirms the normalized value.
    extracted = {"daily_report": {"mw_pcf": 71.8}, "metadata": {"field_provenance": {
        "daily_report.mw_pcf": {"original_value": "9.6", "normalized_value": 71.8}}}}
    plan = ivs.prepare(extracted)
    assert extracted["daily_report"]["mw_pcf"] == 71.8 and plan["fields"]["mw_pcf"]["outcome"] == ivs.NUMBER


def test_a_value_changed_in_the_preview_is_classified_as_it_is():
    extracted = {"daily_report": {"depth_0000": 1500.0}, "metadata": {"field_provenance": {
        "daily_report.depth_0000": {"original_value": "1,500", "normalized_value": 1.5}}}}
    plan = ivs.prepare(extracted)
    assert extracted["daily_report"]["depth_0000"] == 1500.0 and plan["ambiguous"] == []


def test_an_undecided_review_row_stays_the_authority():
    extracted = {"daily_report": {}, "metadata": {
        "field_provenance": {"daily_report.depth_2400": {"original_value": "N/A", "normalized_value": None}},
        "review_matrix": [{"target_field": "daily_report.depth_2400", "decision": "DEFER"}]}}
    plan = ivs.prepare(extracted)
    assert plan["tokens"] == [] and plan["ambiguous"] == [] and "depth_2400" not in extracted["daily_report"]


# ---- real Excel route ---------------------------------------------------------------------------------------
def test_zero_number_blank_token_ambiguous_and_unit_in_one_import(tmp_path, target):
    db, well = target
    extracted = _prepared(tmp_path, {"R9": "1,500", "R10": "N/A", "J14": "12.5 ppg"},
                          accept=("daily_report.depth_2400",))
    result = _import(db, well, extracted)
    report = result["report_id"]
    assert report and result["status"] == "REVIEW_REQUIRED"
    assert sorted(result["value_states"]["ambiguous"]) == ["depth_0000", "mw_pcf"]
    assert [(o["field"], o["outcome"]) for o in result["value_states"]["outcomes"]] == [("depth_2400", ivs.RECORDED)]
    states = vs.states(db, report)
    assert (states["depth_0000"]["value"], states["depth_0000"]["pending_review"]) == (None, "1,500")   # never 1500
    assert (states["mw_pcf"]["value"], states["mw_pcf"]["pending_review"]) == (None, "12.5 ppg")       # never 12.5
    assert (states["depth_2400"]["value"], states["depth_2400"]["state"], states["depth_2400"]["source"]) == \
        (None, vs.NOT_APPLICABLE, "import")
    assert (states["depth_0600"]["value"], states["depth_0600"]["state"]) == (310.0, vs.REPORTED)
    assert not states["wob"]["recorded"] and states["wob"]["state"] == vs.NOT_REPORTED                 # blank
    items = {i["target_field"]: i for i in db.get_import_review_items(well, report_id=report)
             if i["review_type"] == "value_state"}
    assert set(items) == {"daily_report.depth_0000", "daily_report.mw_pcf"}
    assert items["daily_report.depth_0000"]["state"] == "DEFERRED_UNRESOLVED"
    assert items["daily_report.depth_0000"]["original_text"] == "1,500"
    assert "commas are refused" in items["daily_report.depth_0000"]["reason"]
    assert any("Header value states: 1 recorded" in line for line in result["details"])
    assert _counts(db)[1:] == (1, 1)                                                   # one event, one audit


def test_zero_is_stored_as_zero_and_blank_stays_none_without_events(tmp_path, target):
    db, well = target
    zero = _import(db, well, _prepared(tmp_path, {"R9": 0}))
    assert vs.states(db, zero["report_id"])["depth_0000"]["value"] == 0.0
    assert vs.states(db, zero["report_id"])["depth_0000"]["state"] == vs.ZERO
    blank = _import(db, well, _prepared(tmp_path, {"R9": None}))
    entry = vs.states(db, blank["report_id"])["depth_0000"]
    assert (entry["value"], entry["state"], entry["recorded"]) == (None, vs.NOT_REPORTED, False)
    assert _counts(db)[1] == 0


def test_a_deferred_ambiguous_value_is_corrected_strictly_from_the_queue(tmp_path, target):
    from core.review_scalar_correction import CorrectionRefused, apply_correction, preview_correction

    db, well = target
    report = _import(db, well, _prepared(tmp_path, {"R9": "1,500"}))["report_id"]
    item = next(i for i in db.get_import_review_items(well, report_id=report)
                if i["review_type"] == "value_state" and i["target_field"] == "daily_report.depth_0000")
    with pytest.raises(CorrectionRefused):
        preview_correction(db, item["id"], well, "1,500")                    # still refused in the queue
    preview = preview_correction(db, item["id"], well, "1500")
    apply_correction(db, item["id"], well, "1500", reason="read from the paper DDR", confirmed=True,
                     token=preview["token"])
    entry = vs.states(db, report)["depth_0000"]
    assert (entry["value"], entry["state"], entry["pending_review"]) == (1500.0, vs.REPORTED, None)


def test_identical_reimport_writes_no_second_state(tmp_path, target):
    db, well = target
    extracted = _prepared(tmp_path, {"R10": "N/A"}, accept=("daily_report.depth_2400",))
    import copy
    first = _import(db, well, copy.deepcopy(extracted))
    again = _import(db, well, extracted)
    assert again.get("reimport") and again["report_id"] == first["report_id"]
    assert _counts(db) == (1, 1, 1)


def test_an_existing_state_is_kept_and_a_contradiction_is_not_recorded(tmp_path, target):
    db, well = target
    report = _import(db, well, _prepared(tmp_path, {"R9": None}))["report_id"]          # depth_0000 None
    vs.record(db, report, "depth_2400", vs.REPORTED, user_id=None)                      # operator, value 225
    plan = {"tokens": ["depth_2400", "depth_0000", "depth_0600"], "fields": {
        "depth_2400": {"state": vs.NOT_APPLICABLE, "original": "N/A"},
        "depth_0000": {"state": vs.UNKNOWN, "original": "?"},
        "depth_0600": {"state": vs.UNKNOWN, "original": "?"}}}
    with db.session_scope() as session:
        outcomes = {o["field"]: o for o in ivs.record_import_states(db, session, report, plan, fingerprint="f" * 16)}
    assert outcomes["depth_2400"]["outcome"] == ivs.KEPT_EXISTING_STATE and outcomes["depth_2400"]["kept"] == vs.REPORTED
    assert outcomes["depth_0000"]["outcome"] == ivs.RECORDED
    assert outcomes["depth_0600"]["outcome"] == ivs.NOT_RECORDED_CONTRADICTION            # 310 stored: not repaired
    states = vs.states(db, report)
    assert states["depth_2400"]["state"] == vs.REPORTED and states["depth_2400"]["source"] == "operator"
    assert states["depth_0600"]["value"] == 310.0 and not states["depth_0600"]["recorded"]
    assert states["depth_0000"]["source"] == "import"


def test_an_audit_failure_rolls_back_the_whole_import(tmp_path, target, monkeypatch):
    db, well = target
    original = db._add_mandatory_audit

    def failing(session, action, *args, **kwargs):
        if action == ivs.AUDIT_ACTION:
            raise RuntimeError("SYN: audit store unavailable")
        return original(session, action, *args, **kwargs)

    monkeypatch.setattr(db, "_add_mandatory_audit", failing)
    result = _import(db, well, _prepared(tmp_path, {"R10": "N/A"}, accept=("daily_report.depth_2400",)))
    assert result["failed"] >= 1 and result["status"] != "ACCEPT"
    assert any("audit store unavailable" in line for line in result["details"])
    assert _counts(db) == (0, 0, 0)


def test_a_later_import_failure_rolls_the_states_back(tmp_path, target, monkeypatch):
    from core.ddr_import_service import DDRImportService

    db, well = target

    def broken(self, *args, **kwargs):
        raise RuntimeError("SYN: time-log store failed")

    monkeypatch.setattr(DDRImportService, "_save_time_logs", broken)
    result = _import(db, well, _prepared(tmp_path, {"R10": "N/A", "R9": "1,500"}, accept=("daily_report.depth_2400",)))
    assert any("time-log store failed" in line for line in result["details"])
    assert _counts(db) == (0, 0, 0)


def test_the_dialog_shows_the_pending_import_review(tmp_path, target):
    from dialogs.ddr_value_states_dialog import DdrValueStatesDialog

    db, well = target
    report = _import(db, well, _prepared(tmp_path, {"R9": "1,500", "R10": "N/A"},
                                         accept=("daily_report.depth_2400",)))["report_id"]
    dialog = DdrValueStatesDialog(db, report)
    try:
        rows = {dialog.table.item(r, 0).text(): dialog.table.item(r, 4).text() for r in range(dialog.table.rowCount())}
        assert "import review pending: '1,500' (not stored)" in rows["Depth 00:00"]
        assert rows["Depth 24:00"] == "yes (import)"
    finally:
        dialog.deleteLater()
