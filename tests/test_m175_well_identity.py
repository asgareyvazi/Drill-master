"""M175: the selected well versus the well a DDR source names - explicit decision, never silent routing."""
from __future__ import annotations

import json
from datetime import date

import pytest

from core.ddr_well_identity import (
    AMBIGUOUS, CHOOSE_CREATE, CHOOSE_SELECTED, CHOOSE_SOURCE_WELL, CONFLICT_EXISTING, MULTIPLE_IDENTITIES,
    NO_SELECTION_AMBIGUOUS, NO_SELECTION_MATCH, NO_SELECTION_NEW, NO_SOURCE_IDENTITY, OTHER_PROJECT, SAME,
    UNKNOWN_SOURCE_WELL, WellIdentityRefused, WellRef, assess, make_decision, source_identity, validate_decision,
)

A1 = WellRef(1, "AZNS-207", "AZ207", 10, "North")
A2 = WellRef(2, "AZNS-208", "AZ208", 10, "North")
B1 = WellRef(3, "AZNS-207", "B207", 20, "South")      # same name, another project
WELLS = [A1, A2, B1]


# ---- pure contract ----------------------------------------------------------------------------------------
def test_same_well_and_missing_source_identity_import_into_the_selected_well():
    assert assess(A1, {"name": "AZNS-207"}, WELLS).status == SAME
    assert assess(A1, {"name": "azns 207"}, WELLS).status == SAME          # catalogue label equivalence
    assert assess(A1, {"code": "AZ207"}, WELLS).status == SAME
    missing = assess(A1, {}, WELLS)
    assert missing.status == NO_SOURCE_IDENTITY and validate_decision(missing, None) == (1, False)


def test_another_existing_well_requires_a_decision_and_shows_both_identities():
    result = assess(A1, {"well_name": "AZNS-208"}, WELLS)
    assert result.status == CONFLICT_EXISTING and result.requires_decision
    assert result.matches == [A2] and result.options == (CHOOSE_SELECTED, CHOOSE_SOURCE_WELL)
    assert result.evidence == [{"field": "well_name", "value": "AZNS-208", "role": "name"}]
    assert "AZNS-207" in result.message and "AZNS-208" in result.message and len(result.consequences) == 2
    with pytest.raises(WellIdentityRefused, match="NOT SAVED"):
        validate_decision(result, None)


def test_similar_names_never_match_and_never_create_silently():
    result = assess(A1, {"name": "AZNS-207A"}, WELLS)
    assert result.status == UNKNOWN_SOURCE_WELL and result.matches == []
    assert result.options == (CHOOSE_SELECTED, CHOOSE_CREATE)
    with pytest.raises(WellIdentityRefused):
        validate_decision(result, None)
    assert validate_decision(result, make_decision(result, CHOOSE_CREATE, "new well")) == (None, True)
    assert validate_decision(result, make_decision(result, CHOOSE_SELECTED, "typo in the DDR")) == (1, False)


def test_duplicate_names_in_different_projects():
    # Selected in North: the North well wins (project scope) -> same well.
    assert assess(A1, {"name": "AZNS-207"}, WELLS).status == SAME
    # Selected in South with the North code: another project -> only the selected well can be chosen.
    other = assess(B1, {"code": "AZ207"}, WELLS)
    assert other.status == OTHER_PROJECT and other.options == (CHOOSE_SELECTED,)
    with pytest.raises(ValueError):
        make_decision(other, CHOOSE_SOURCE_WELL, "x")
    # No selection: two wells share the name -> refused, nothing created.
    refused = assess(None, {"name": "AZNS-207"}, WELLS, project_count=2)
    assert refused.status == NO_SELECTION_AMBIGUOUS and refused.refused and "ambiguous" in refused.message
    # The refusal itself is reported (no choice can fix it), not a request to choose a target.
    with pytest.raises(WellIdentityRefused, match="ambiguous") as raised:
        validate_decision(refused, None)
    assert "Choose the target well" not in str(raised.value)


def test_several_matches_in_scope_and_contradictory_name_and_code_are_refused():
    twins = [A1, WellRef(9, "AZNS-207", "", 10, "North")]
    assert assess(A2, {"name": "AZNS-207"}, twins + [A2]).status == AMBIGUOUS
    contradictory = assess(A1, {"name": "AZNS-208", "code": "AZ207"}, WELLS)
    assert contradictory.status == MULTIPLE_IDENTITIES and {m.id for m in contradictory.matches} == {1, 2}
    with pytest.raises(WellIdentityRefused):
        validate_decision(contradictory, {"choice": CHOOSE_SELECTED, "reason": "x"})


def test_no_selection():
    assert assess(None, {}, WELLS).status == NO_SELECTION_AMBIGUOUS
    match = assess(None, {"code": "AZ208"}, WELLS, project_count=2)
    assert match.status == NO_SELECTION_MATCH and validate_decision(match, None) == (2, False)
    assert assess(None, {"name": "NEW-1"}, WELLS, project_count=1).status == NO_SELECTION_NEW
    assert assess(None, {"name": "NEW-1"}, WELLS, project_count=2).status == NO_SELECTION_AMBIGUOUS


def test_a_stale_or_tampered_decision_is_refused():
    conflict = assess(A1, {"name": "AZNS-208"}, WELLS)
    decision = make_decision(conflict, CHOOSE_SOURCE_WELL, "the DDR belongs to 208")
    assert validate_decision(conflict, decision) == (2, False)
    # The selection changed after the decision (context switch during extraction).
    with pytest.raises(WellIdentityRefused, match="selected well changed"):
        validate_decision(assess(A2, {"name": "AZNS-207"}, WELLS), decision)
    # The source identity is not the one decided.
    with pytest.raises(WellIdentityRefused, match="source identity"):
        validate_decision(assess(A1, {"name": "AZNS-208", "code": "AZ208"}, WELLS), decision)
    for key, value in (("target_well_id", 3), ("reason", " "), ("choice", CHOOSE_CREATE), ("contract", "v0")):
        with pytest.raises(WellIdentityRefused):
            validate_decision(conflict, {**decision, key: value})
    # The database changed: the unknown well now exists.
    unknown = assess(A1, {"name": "NEW-9"}, WELLS)
    created = make_decision(unknown, CHOOSE_CREATE, "new")
    with pytest.raises(WellIdentityRefused, match="database identity changed"):
        validate_decision(assess(A1, {"name": "NEW-9"}, WELLS + [WellRef(7, "NEW-9", "", 10)]), created)


def test_a_decision_needs_a_reason_and_an_offered_choice():
    conflict = assess(A1, {"name": "AZNS-208"}, WELLS)
    with pytest.raises(ValueError, match="reason"):
        make_decision(conflict, CHOOSE_SELECTED, "  ")
    with pytest.raises(ValueError):
        make_decision(conflict, CHOOSE_CREATE, "x")
    with pytest.raises(ValueError):
        make_decision(assess(A1, {"name": "AZNS-207"}, WELLS), CHOOSE_SELECTED, "x")


def test_source_identity_keeps_the_cell_evidence():
    name, code, evidence = source_identity({"name": " X-1 ", "code": "", "well_code": "C1",
                                            "_source_cells": {"well_info.name": "B3"}})
    assert (name, code) == ("X-1", "C1")
    assert evidence == [{"field": "name", "value": "X-1", "role": "name", "cell": "B3"},
                        {"field": "well_code", "value": "C1", "role": "code"}]


# ---- persistence on a fresh file-backed database ------------------------------------------------------------
@pytest.fixture
def db(tmp_path):
    from core.database import DatabaseManager, Project, Well

    manager = DatabaseManager()
    manager.db_path = str(tmp_path / "m175.db")
    assert manager.initialize()
    with manager.session_scope() as session:
        north = Project(name="North", code="N-M175", company_id=1)
        south = Project(name="South", code="S-M175", company_id=1)
        session.add_all([north, south])
        session.flush()
        wells = [Well(name="M175-A", code="M175A", project_id=north.id),
                 Well(name="M175-B", code="M175B", project_id=north.id),
                 Well(name="M175-A", code="M175S", project_id=south.id)]
        session.add_all(wells)
        session.flush()
        manager.m175 = {"a": wells[0].id, "b": wells[1].id, "south": wells[2].id}
    yield manager
    manager.close()


def _payload(well_info, day=1):
    return {"well_info": dict(well_info), "daily_report": {"report_date": date(2026, 10, day)},
            "time_logs_24h": [{"time_from": "00:00", "time_to": "06:00", "activity_description": "Drill",
                               "_source_row": 2}],
            "metadata": {"source_file": f"m175-{day}.xlsx"}}


def _service(db, well_id):
    from core.ddr_import_service import DDRImportService
    return DDRImportService(db, well_id)


def _reports(db):
    from core.database import DailyReport, Well
    with db.session_scope() as session:
        return ([(r.id, r.well_id) for r in session.query(DailyReport).order_by(DailyReport.id)],
                session.query(Well).count())


def test_conflict_saves_nothing_without_a_decision(db):
    before = _reports(db)
    result = _service(db, db.m175["a"]).import_records(_payload({"name": "M175-B"}))
    assert result["status"] == "VALIDATION_ERROR" and not result["report_id"] and result["failed"] == 1
    assert result["well_identity"]["assessment"]["status"] == CONFLICT_EXISTING
    assert any(d.get("stage") == "import.well_identity" for d in result["diagnostics"])
    assert result["details"][-1].startswith("❌ NOT SAVED")
    assert _reports(db) == before


def test_operator_choice_routes_explicitly_and_is_audited(db):
    from core.database import AuditLog, Well
    service = _service(db, db.m175["a"])
    payload = _payload({"name": "M175-B", "rig_name": "SOURCE RIG"})
    payload["metadata"]["well_identity_decision"] = make_decision(
        service.assess_well_identity(payload["well_info"]), CHOOSE_SELECTED, "header copied from 208 by mistake")
    result = service.import_records(payload)
    assert result["report_id"] and result["well_id"] == db.m175["a"], result
    assert any("evidence only" in line for line in result["details"])
    with db.session_scope() as session:
        selected = session.get(Well, db.m175["a"])
        assert (selected.name, selected.code) == ("M175-A", "M175A")       # master data not overwritten
        audit = session.query(AuditLog).filter_by(action="ddr_well_identity_decision").one()
        details = json.loads(audit.details)
        assert audit.entity_id == db.m175["a"] and details["choice"] == CHOOSE_SELECTED
        assert details["source"]["name"] == "M175-B" and details["reason"] and details["matches"] == [db.m175["b"]]
        assert details["status"] == CONFLICT_EXISTING and details["selected"] == details["target"] == db.m175["a"]
        imported = json.loads(session.query(AuditLog).filter_by(action="ddr_import").one().details)
        assert imported["result"]["well_identity"]["decision"]["choice"] == CHOOSE_SELECTED


def test_choosing_the_source_well_and_creating_a_well(db):
    service = _service(db, db.m175["a"])
    payload = _payload({"name": "M175-B"}, day=2)
    payload["metadata"]["well_identity_decision"] = make_decision(
        service.assess_well_identity(payload["well_info"]), CHOOSE_SOURCE_WELL, "the DDR is the B well's")
    assert service.import_records(payload)["well_id"] == db.m175["b"]

    creator = _service(db, db.m175["a"])
    fresh = _payload({"name": "M175-NEW", "code": "M175N"}, day=3)
    reports, wells = _reports(db)
    refused = creator.import_records(fresh)
    assert refused["well_identity"]["assessment"]["status"] == UNKNOWN_SOURCE_WELL and _reports(db)[1] == wells
    fresh["metadata"]["well_identity_decision"] = make_decision(
        creator.assess_well_identity(fresh["well_info"]), CHOOSE_CREATE, "first DDR of a new well")
    created = creator.import_records(fresh)
    assert created["report_id"] and created["well_id"] not in db.m175.values() and _reports(db)[1] == wells + 1


def test_stale_decision_and_foreign_project_are_refused_at_persistence(db):
    service = _service(db, db.m175["a"])
    payload = _payload({"name": "M175-B"}, day=4)
    payload["metadata"]["well_identity_decision"] = make_decision(
        service.assess_well_identity(payload["well_info"]), CHOOSE_SOURCE_WELL, "x")
    before = _reports(db)
    stale = _service(db, db.m175["south"]).import_records(payload)        # selection changed meanwhile
    assert stale["status"] == "VALIDATION_ERROR" and "no longer valid" in stale["details"][-1]
    foreign = _service(db, db.m175["south"])
    other = foreign.assess_well_identity({"code": "M175B"})
    assert other.status == OTHER_PROJECT and other.options == (CHOOSE_SELECTED,)
    assert _reports(db) == before


def test_reimport_is_idempotent_and_saves_nothing_new(db):
    service = _service(db, db.m175["a"])
    payload = _payload({"name": "M175-A"}, day=5)
    first = service.import_records(payload)
    assert first["report_id"] and first["well_id"] == db.m175["a"]
    before = _reports(db)
    again = _service(db, db.m175["a"]).import_records(payload)
    assert again["reimport"] and again["report_id"] == first["report_id"] and "nothing saved" in again["details"][0]
    assert _reports(db) == before


def test_legacy_resolver_never_switches_or_creates_silently(db):
    service = _service(db, db.m175["a"])
    with pytest.raises(WellIdentityRefused):
        service._resolve_import_well({"name": "M175-B"})
    with pytest.raises(WellIdentityRefused):
        service._resolve_import_well({"name": "M175-ZZZ"})
    assert service.well_id == db.m175["a"] and _reports(db)[1] == 3 + _base_wells(db)
    assert service._resolve_import_well({"name": "m175 a"}) == db.m175["a"]


def _base_wells(db):
    from core.database import Well
    with db.session_scope() as session:
        return session.query(Well).filter(~Well.id.in_(list(db.m175.values()))).count()


# ---- real Qt: the decision dialog and the import-dialog hook --------------------------------------------
@pytest.fixture
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_dialog_requires_a_choice_and_a_reason_and_preselects_nothing(qapp):
    from PySide6.QtWidgets import QDialogButtonBox
    from dialogs.well_identity_dialog import WellIdentityDialog

    conflict = assess(A1, {"name": "AZNS-208", "_source_cells": {"well_info.name": "C4"}}, WELLS)
    dialog = WellIdentityDialog(conflict, decided_by="tester")
    ok = dialog.button_box.button(QDialogButtonBox.Ok)
    assert dialog.chosen() is None and not ok.isEnabled()
    assert "cell C4" in dialog.evidence_label.text()
    dialog.buttons[CHOOSE_SOURCE_WELL].setChecked(True)
    assert not ok.isEnabled()
    dialog.reason.setText("belongs to 208")
    assert ok.isEnabled()
    ok.click()
    assert dialog.decision["choice"] == CHOOSE_SOURCE_WELL and dialog.decision["target_well_id"] == 2
    assert dialog.decision["decided_by"] == "tester" and validate_decision(conflict, dialog.decision) == (2, False)
    dialog.deleteLater()


def test_import_dialog_asks_and_a_cancel_saves_nothing(qapp, db, monkeypatch):
    from dialogs.excel_import_dialog import ExcelImportDialog

    dialog = ExcelImportDialog(db, db.m175["a"])
    asked = []
    monkeypatch.setattr(dialog, "_ask_well_identity", lambda assessment: asked.append(assessment.status) or None)
    payload = _payload({"name": "M175-B"}, day=6)
    assert dialog._confirm_well_identity(payload) is False and asked == [CONFLICT_EXISTING]
    assert "well_identity_decision" not in payload["metadata"]
    same = _payload({"name": "M175-A"}, day=6)
    assert dialog._confirm_well_identity(same) is True and asked == [CONFLICT_EXISTING]   # no question
    monkeypatch.setattr(dialog, "_ask_well_identity",
                        lambda assessment: make_decision(assessment, CHOOSE_SELECTED, "operator"))
    assert dialog._confirm_well_identity(payload) is True
    assert payload["metadata"]["well_identity_decision"]["selected_well_id"] == db.m175["a"]
    dialog.deleteLater()


def test_the_target_decision_is_not_part_of_the_source_fingerprint():
    from core.ddr_import_service import _source_fingerprint

    payload = {"well_info": {"well_name": "SYN-1"}, "metadata": {"source": "x"}}
    decided = {"well_info": {"well_name": "SYN-1"},
               "metadata": {"source": "x", "well_identity_decision": {"choice": "SELECTED", "decided_at": "t1"}}}
    redecided = {"well_info": {"well_name": "SYN-1"},
                 "metadata": {"source": "x", "well_identity_decision": {"choice": "SELECTED", "decided_at": "t2"}}}
    assert _source_fingerprint(payload) == _source_fingerprint(decided) == _source_fingerprint(redecided)
    assert _source_fingerprint(payload) != _source_fingerprint({"well_info": {"well_name": "SYN-2"},
                                                                "metadata": {"source": "x"}})


def test_an_equivalent_spelling_on_another_well_is_ambiguous_not_routed_to_the_exact_spelling():
    twin = WellRef(9, "AZNS 207", "", 10, "North")           # catalogue-equivalent to A1 "AZNS-207"
    wells = [A1, A2, twin]
    for spelling in ("AZNS-207", "AZNS 207", "azns-207"):
        result = assess(A2, {"name": spelling}, wells)
        assert result.status == AMBIGUOUS and {m.id for m in result.matches} == {1, 9} and result.refused
    # The selected well is an exact spelling of the source: that is the target, the twin stays as evidence.
    same = assess(A1, {"name": "AZNS-207"}, wells)
    assert same.status == SAME and same.matches == [A1]
    assert any(e.get("role") == "twin" and "AZNS 207" in e["value"] for e in same.evidence)
    # Only an equivalent (not exact) spelling of the selected well with a twin: still ambiguous.
    assert assess(A1, {"name": "azns 207"}, wells).status == AMBIGUOUS
