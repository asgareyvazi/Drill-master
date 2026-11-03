"""M94: user journeys A–R through the desktop UI.

Two parts:

1. **Connected journeys** through one real MainWindow (offscreen Qt, synthetic database from the M70
   fixture): select a well → W12 Operational Analysis → drill-down to the source report → W11 report export
   (real export worker) with provenance → switch well: no data of the previous well remains → a Persian-named
   well exported right-to-left.
2. **Journey register**: every journey A–R maps to UI-path tests; a test fails if any referenced test function
   no longer exists, so the register cannot silently go stale.

Offscreen runs are not Windows desktop acceptance (see packaging/WINDOWS_RELEASE_ACCEPTANCE.md).
"""
from __future__ import annotations

import ast
import time
from pathlib import Path

import pytest

from core.selection_manager import SelectionManager
from test_m70_selection_audit import _pump, window  # noqa: F401  (module fixture reused)

TESTS = Path(__file__).resolve().parent

# journey -> (description, [test file::function, ...]); every entry runs a UI path or the service it calls.
JOURNEYS = {
    "A": ("Context: select / switch / clear well, no leakage", [
        "test_m83_selection_lifecycle.py::test_switching_wells_leaves_no_identifier_of_the_previous_well",
        "test_m83_selection_lifecycle.py::test_clear_leaves_an_empty_state_and_clean_edit_baselines"]),
    "B": ("DDR authoring: edit, reorder, navigate, unsaved edits", [
        "test_m52_ddr_manual_edit.py::test_a_reordered_time_log_survives_save_and_reload",
        "test_m52_ddr_manual_edit.py::test_unsaved_edits_are_not_discarded_without_confirmation",
        "test_m52_ddr_manual_edit.py::test_previous_and_next_follow_date_order_and_stop_at_the_ends"]),
    "C": ("DDR batch import: worker, cancel, file identity", [
        "test_m71_ddr_background.py::test_cancel_during_preparation_saves_nothing_and_cancels_the_rest",
        "test_m71_ddr_background.py::test_a_late_result_cannot_be_saved_for_another_well",
        "test_m84_ddr_identity_cleanup.py::test_a_file_changed_during_preview_is_never_saved"]),
    "D": ("Survey: revision, reference declaration, conversion", [
        "test_m72_survey_ui.py::test_freeze_import_preview_and_compare_from_the_panel",
        "test_m85_survey_references.py::test_panel_requires_declaration_and_converts_with_explicit_values"]),
    "E": ("Directional plan from an inclined tie-in", [
        "test_m86_directional_solver.py::test_designer_panel_solves_from_an_inclined_survey_tie_in",
        "test_m72_survey_ui.py::test_designer_ties_in_solves_and_hands_a_continuous_plan_to_compare"]),
    "F": ("Plan vs actual / closest approach (SCREENING)", [
        "test_m52_trajectory_compare.py::test_closest_approach_between_skew_lines_is_found_between_stations",
        "test_m52_trajectory_compare.py::test_unconfirmed_crs_and_missing_datum_are_not_assessed_with_every_reason"]),
    "G": ("Well architecture revision and cement worksheet", [
        "test_m74_well_architecture.py::test_w3b_architecture_page_freezes_reloads_and_derives_cement",
        "test_m89_architecture_casing_cement.py::test_w3b_cement_worksheet_with_caliper_and_excess_is_saved_with_lineage"]),
    "H": ("W13 case: save, reopen, re-run, clone, export", [
        "test_m87_w13_contracts.py::test_bit_case_save_reopen_rerun_clone_export_and_verify",
        "test_m89_architecture_casing_cement.py::test_w13_casing_from_architecture_reaches_history_with_lineage"]),
    "I": ("History lineage and navigation", [
        "test_m88_history_lineage.py::test_history_tab_opens_a_linked_record_on_another_page",
        "test_m88_history_lineage.py::test_lineage_follows_revision_chains_and_the_architecture_survey_link"]),
    "J": ("Operational analysis with drill-down", [
        "test_m91_operational_analysis.py::test_w12_page_refresh_drilldown_invalidation_and_export",
        "test_m94_e2e_journeys.py::test_journey_context_to_operational_analysis_drilldown_and_switch"]),
    "K": ("Report export with provenance", [
        "test_m93_report_provenance.py::test_every_engine_writes_provenance_in_every_format",
        "test_m94_e2e_journeys.py::test_journey_report_export_through_w11_carries_the_selected_well_only"]),
    "L": ("Stale async results are discarded", [
        "test_m83_selection_lifecycle.py::test_context_token_changes_on_every_selection_event",
        "test_m71_ddr_background.py::test_a_late_result_cannot_be_saved_for_another_well"]),
    "M": ("Well delete: history goes with the well, audited, authorised", [
        "test_m70_integrity.py::test_deleting_a_well_removes_its_history_rows_with_one_audit_record",
        "test_m70_integrity.py::test_a_viewer_cannot_delete_a_well_with_history",
        "test_m83_selection_lifecycle.py::test_deleting_the_project_of_the_selected_well_clears_the_selection"]),
    "N": ("Backup / restore", [
        "test_backup_restore_acceptance.py::test_file_database_backup_corruption_restore_and_reopen",
        "test_m80_recovery_offline.py::test_restore_brings_back_revisions_with_their_immutability_guards"]),
    "O": ("Offline: no network library on the product path", [
        "test_m80_recovery_offline.py::test_new_modules_import_no_network_library"]),
    "P": ("Language: Persian data, right-to-left output", [
        "test_m49_knowledge_ui.py::test_persian_answer_is_right_to_left_and_long_passages_are_elided",
        "test_m93_report_provenance.py::test_rtl_reaches_html_pdf_layout_and_excel",
        "test_m94_e2e_journeys.py::test_journey_persian_well_report_right_to_left"]),
    "Q": ("Method catalogue, no self-approval", [
        "test_m92_method_catalogue.py::test_help_menu_opens_a_read_only_catalogue",
        "test_m92_method_catalogue.py::test_no_self_approval"]),
    "R": ("Authorisation: viewers cannot write", [
        "test_m85_survey_references.py::test_a_viewer_cannot_save_a_conversion",
        "test_m74_well_architecture.py::test_viewers_cannot_save_an_architecture"]),
}


def _functions(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def test_journey_register_covers_a_to_r_with_existing_tests():
    assert sorted(JOURNEYS) == [chr(c) for c in range(ord("A"), ord("R") + 1)]
    missing = []
    for letter, (_title, refs) in JOURNEYS.items():
        assert refs, letter
        for ref in refs:
            file, func = ref.split("::")
            if not (TESTS / file).exists() or func not in _functions(TESTS / file):
                missing.append(f"{letter}: {ref}")
    assert missing == []


def _tab(win, name):
    for i in range(win.tab_widget.count()):
        widget = win.tab_widget.widget(i)
        if type(widget).__name__ == name:
            win.tab_widget.setCurrentWidget(widget)
            _pump(0.3)
            return widget
    raise LookupError(name)


@pytest.fixture
def no_prompts(monkeypatch):
    import tabs.w2_Daily_Report as w2
    monkeypatch.setattr(w2.QMessageBox, "question", staticmethod(lambda *a, **k: w2.QMessageBox.No))


def test_journey_context_to_operational_analysis_drilldown_and_switch(window, no_prompts):  # noqa: F811
    win, _db, ids = window
    win.navigate_to({"type": "well", "id": ids["alpha"]})
    _pump(0.4)
    w12 = _tab(win, "AnalysisWidget")
    w12.analysis_tabs.setCurrentWidget(w12.operational_panel)
    panel = w12.operational_panel
    assert panel.refresh() is not None                   # M103: background job on the file database
    result = panel.wait()
    assert result is not None and "SYN-ALPHA-01" in result.scope_label
    daily = panel.tables["daily"]
    assert daily.rowCount() == 2 and daily.item(0, 4).text() == "—"     # no 00:00 depth: footage unknown, not 0
    panel.tabs.setCurrentIndex(panel.tabs.indexOf(panel.tables["daily"]))
    daily.selectRow(1)
    assert panel.open_selected()
    _pump(0.3)
    assert SelectionManager().current_report_id == ids["report_2"]
    win.navigate_to({"type": "well", "id": ids["twin_1"]})
    _pump(0.4)
    assert panel.result is None and panel.tables["daily"].rowCount() == 0
    assert "SYN-ALPHA" not in panel.summary.text()


def _export_eowr(win, monkeypatch, path, direction):
    import tabs.w11_Export as w11
    tab = _tab(win, "ExportWidget")
    monkeypatch.setattr(w11.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(path), "")))
    tab.eowr_fmt.setCurrentText("HTML")
    tab.direction_combo.setCurrentIndex(tab.direction_combo.findData(direction))
    tab._export_eowr()
    end = time.monotonic() + 30
    while tab.export_running() and time.monotonic() < end:
        _pump(0.05)
    assert not tab.export_running() and path.exists(), tab.eowr_status.text()
    return path.read_text(encoding="utf-8")


def test_journey_report_export_through_w11_carries_the_selected_well_only(window, no_prompts, monkeypatch,  # noqa: F811
                                                                          tmp_path):
    from core import report_provenance as rp
    win, _db, ids = window
    win.navigate_to({"type": "well", "id": ids["alpha"]})
    _pump(0.4)
    text = _export_eowr(win, monkeypatch, tmp_path / "alpha.html", "ltr")
    assert rp.LABEL in text and f"SYN-ALPHA-01 (id {ids['alpha']})" in text and 'dir="ltr"' in text
    win.navigate_to({"type": "well", "id": ids["twin_1"]})
    _pump(0.4)
    text = _export_eowr(win, monkeypatch, tmp_path / "twin.html", "ltr")
    assert f"(id {ids['twin_1']})" in text and "SYN-ALPHA-01" not in text


def test_journey_persian_well_report_right_to_left(window, no_prompts, monkeypatch, tmp_path):  # noqa: F811
    win, _db, ids = window
    win.navigate_to({"type": "well", "id": ids["persian"]})
    _pump(0.4)
    text = _export_eowr(win, monkeypatch, tmp_path / "fa.html", "rtl")
    assert "چاه نمونه ۷" in text and 'dir="rtl"' in text
