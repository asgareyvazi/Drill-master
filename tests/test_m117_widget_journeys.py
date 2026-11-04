"""M117: user journeys walked through the real desktop widgets that had no widget-level test yet -
G survey integrity, M NOT_REPRODUCIBLE, U multi-report workbook, X offline, Z delete isolation.

Every journey drives the production tab/panel (no fake window, no stand-in widget) on SYNTHETIC data in a
temporary SQLite database. Offscreen Qt on Linux - not a Windows desktop or field acceptance.
"""
from __future__ import annotations

import json
import os
import socket
import sqlite3
from datetime import date
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from core import survey_revisions as sr  # noqa: E402
from tests.test_m70_integrity import _open, _seed  # noqa: E402

STATIONS = [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": 300.0, "inc": 0.0, "azi": 0.0},
            {"md": 600.0, "inc": 20.0, "azi": 357.0}, {"md": 900.0, "inc": 35.0, "azi": 10.0}]


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def env(app, tmp_path, monkeypatch):
    path = tmp_path / "m117.sqlite"
    manager = _open(path, tmp_path, monkeypatch)
    ids = _seed(manager)
    yield manager, path, ids
    manager.close()


def _no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("this journey must not open a network connection")
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


# ---- G: survey integrity -----------------------------------------------------------------------------
def test_journey_g_a_tampered_survey_is_shown_as_such_and_refused_for_use(env):
    from tabs.survey_revision_panel import COLUMNS, SurveyRevisionPanel

    manager, path, ids = env
    well = ids["A"][0]
    good = sr.save_revision(manager, well, STATIONS, depth_datum="RKB", azimuth_reference="magnetic")
    bad = sr.save_revision(manager, well, STATIONS, depth_datum="RKB", azimuth_reference="magnetic")
    manager.close()
    with sqlite3.connect(path) as con:                     # out-of-band tamper, as an outside tool would
        for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='trigger' "
                                   "AND name LIKE 'trg_survey_revision_immutable%'").fetchall():
            con.execute(f"DROP TRIGGER {name}")
        results = json.loads(con.execute("SELECT results_json FROM survey_revisions WHERE id=?",
                                         (bad["id"],)).fetchone()[0])
        results[-1]["tvd"] = float(results[-1]["tvd"]) + 5.0
        con.execute("UPDATE survey_revisions SET results_json=? WHERE id=?", (json.dumps(results), bad["id"]))
    manager.initialize()                                   # restart re-installs the guards; data is not repaired
    panel = SurveyRevisionPanel(manager)
    try:
        panel.set_well(well)
        col = COLUMNS.index("Results hash")
        shown = {panel.revisions[r]["id"]: panel.table.item(r, col).text() for r in range(panel.table.rowCount())}
        assert shown == {good["id"]: "VERIFIED", bad["id"]: "HASH MISMATCH"}
        row = next(r for r in range(len(panel.revisions)) if panel.revisions[r]["id"] == bad["id"])
        panel.table.selectRow(row)
        panel.target_combo.setCurrentIndex(panel.target_combo.findData("true"))
        panel.declination_edit.setText("4.5")
        panel.param_source_edit.setText("SYN contractor sheet")
        panel.param_date_edit.setText("2026-10-01")
        assert panel.convert_selected() is None
        assert "Not converted" in panel.status.text() and "SHA-256" in panel.status.text()
        assert panel.table.rowCount() == 2                 # nothing was derived from the tampered revision
        assert sr.get_revision(manager, bad["id"])["results_integrity"] == "HASH MISMATCH"   # never repaired
        row = next(r for r in range(len(panel.revisions)) if panel.revisions[r]["id"] == good["id"])
        panel.table.selectRow(row)                         # positive control: the intact revision converts
        assert panel.convert_selected()["azimuth_reference"] == "true"
    finally:
        panel.deleteLater()


# ---- M: NOT_REPRODUCIBLE -------------------------------------------------------------------------------
def test_journey_m_a_legacy_record_is_not_reproducible_in_the_history_tab(env, app):
    from core import trajectory_compare as tc
    from core.database import TrajectoryCalculation
    from tabs.calculation_history_tab import COLUMNS, CalculationHistoryTab

    manager, _path, ids = env
    well = ids["A"][0]
    with manager.session_scope() as session:              # the shape of a record saved before M108
        row = TrajectoryCalculation(well_id=well, method=tc.METHOD_VERSION, calculation_date=date(2026, 1, 2),
                                    parameters_json={"contract": tc.CONTRACT, "inputs": {"actual_stations": 4}},
                                    results_json={"status": "ASSESSED", "rows": []}, description=tc.LABEL)
        session.add(row)
        session.flush()
        legacy_id = row.id
    tab = CalculationHistoryTab(manager)
    try:
        tab.set_well(well)
        rows = [i for i, e in enumerate(tab.entries) if e.source == "Trajectory" and e.record_id == legacy_id]
        assert len(rows) == 1
        assert tab.table.item(rows[0], COLUMNS.index("Version")).text() == "unversioned (legacy)"
        tab.select_rows(rows)
        assert "Reproducible: NOT REPRODUCIBLE" in tab.statuses_label.text()
        assert tab.recalc_btn.isEnabled()
        outcome = tab.recalculate()
        assert outcome["status"] == "NOT_REPRODUCIBLE" and "before M108" in outcome["detail"]
        assert "Recalculation: NOT_REPRODUCIBLE" in tab.status.text()
        assert not tab.save_recalc_btn.isEnabled()        # nothing to store; the current method is never assigned
        with manager.session_scope() as session:
            assert session.get(TrajectoryCalculation, legacy_id).method_version in (None, "")
    finally:
        tab.deleteLater()
        app.processEvents()


# ---- U: multi-report workbook --------------------------------------------------------------------------
def test_journey_u_w11_writes_one_professional_workbook_per_report(env, app, tmp_path, monkeypatch):
    from openpyxl import load_workbook

    import tabs.w11_Export as module
    from core.database import DailyReport

    manager, _path, ids = env
    well, bore = ids["A"]
    with manager.session_scope() as session:
        first = DailyReport(well_id=well, wellbore_id=bore, report_date=date(2026, 1, 2), report_number=7)
        second = DailyReport(well_id=well, report_date=date(2026, 1, 5), report_number=8)
        session.add_all([first, second])
        session.flush()
        report_ids = {7: first.id, 8: second.id}
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.setattr(module.QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(out)))
    monkeypatch.setattr(module.QMessageBox, "information", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(module.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(module.ExportWidget, "_open_output", staticmethod(lambda path: None))
    widget = module.ExportWidget(db_manager=manager)
    try:
        index = widget.batch_well.findData(well)
        assert index >= 0
        widget.batch_well.setCurrentIndex(index)
        for box in (widget.batch_ddr, widget.batch_eowr, widget.batch_npt, widget.batch_cost, widget.batch_plan):
            box.setChecked(False)
        widget.batch_professional.setChecked(True)
        widget.batch_professional_per_report.setChecked(True)
        widget.batch_fmt.setCurrentText("HTML")
        widget._export_batch()
        worker = widget._export_worker
        assert worker is not None and worker.wait(120000)
        for _ in range(5):
            app.processEvents()
        assert not widget.export_running()
        books = {name for name in os.listdir(out) if name.startswith("Professional_16Sheets_")}
        dates = {7: "2026-01-02", 8: "2026-01-05"}
        per_report = {num: [b for b in books if f"_{num}_{dates[num]}_" in b] for num in dates}
        assert all(len(found) == 1 for found in per_report.values()), (books, widget.batch_log.toPlainText())
        per_report = {num: found[0] for num, found in per_report.items()}
        for number, name in per_report.items():
            book = load_workbook(out / name, read_only=True)
            prov = {(r[0], r[1]) for r in book["Provenance"].iter_rows(values_only=True) if r and r[0]}
            scopes = {value for key, value in prov if key == "scope.report"}
            assert scopes == {f"#{number} of {dates[number]} (id {report_ids[number]})"}   # its own report only
            assert ("revision", "Report revision: none recorded") in prov                 # never "Rev 0"
            book.close()
        assert "❌" not in widget.batch_log.toPlainText()
    finally:
        widget.deleteLater()
        app.processEvents()


# ---- X and Z: documents tab offline, and deleting one well leaves the others intact -------------------------
@pytest.fixture
def documents(app, tmp_path):
    from document_link_fixtures import build_link_world, import_documents, without_session_user, write_documents
    from test_scope_attribution import _mgr

    from core.document_links import DocumentLinkService
    from tabs.documents_tab import DocumentsTab

    with without_session_user():
        db = _mgr()
        ids = build_link_world(db)
        ids["docs"] = import_documents(db, write_documents(tmp_path / "docs"))
        links = DocumentLinkService(db)
        links.create_link(ids["docs"]["alpha"], ids["alpha"], page_no=2)
        links.create_link(ids["docs"]["twin"], ids["twin_1"])
        widget = DocumentsTab(db)
        widget.show_dialogs = False
        try:
            yield widget, db, ids
        finally:
            widget.cleanup()
            widget.deleteLater()
            db.engine.dispose()


def _scope(widget, key):
    widget.filter_combo.setCurrentIndex(next(i for i in range(widget.filter_combo.count())
                                             if widget.filter_combo.itemData(i) == key))


def _hits(widget):
    return {hit["document_id"] for hit in widget.last_search["hits"]}


def test_journey_x_the_documents_tab_works_with_no_network(documents, monkeypatch):
    widget, _db, ids = documents
    _no_network(monkeypatch)
    widget.on_context_changed(SimpleNamespace(well_id=ids["alpha"]))
    _scope(widget, "selected_well")
    widget.search_edit.setText("mud weight")
    widget.run_search()
    assert _hits(widget) == {ids["docs"]["alpha"]}
    texts = [widget.results.item(i).text() for i in range(widget.results.count())]
    assert texts and all("syn_alpha_daily.txt" in t for t in texts)               # file and page cited
    assert all(hit["page_no"] >= 1 for hit in widget.last_search["hits"])
    widget.search_edit.setText("nonexistentsyntheticterm")
    widget.run_search()
    assert widget.results.count() == 0 and widget.last_search["status"] == "no_matches"
    assert "text layer" in widget.last_search["message"]                          # honest, never "no data"


def test_journey_z_deleting_one_well_leaves_every_other_well_intact(documents):
    from core.database import DailyReport, DocumentLink, Well

    widget, db, ids = documents
    widget.on_context_changed(SimpleNamespace(well_id=ids["alpha"]))
    _scope(widget, "selected_well")
    widget.search_edit.setText("SYNTHETIC")
    widget.run_search()
    assert _hits(widget) == {ids["docs"]["alpha"]}
    assert db.delete_hierarchy_entity("well", ids["twin_1"]) is True               # the audited service delete
    widget.refresh()                                                               # what the window does next
    assert _hits(widget) == {ids["docs"]["alpha"]}                                 # the open search is unchanged
    with db.session_scope() as session:
        assert session.get(Well, ids["twin_1"]) is None
        for keep in ("alpha", "twin_2", "persian"):
            assert session.get(Well, ids[keep]) is not None
        assert session.query(DailyReport).filter_by(well_id=ids["alpha"]).count() == 2
        assert session.get(DailyReport, ids["twin_report"]) is None
        linked = {(link.document_id, link.well_id) for link in session.query(DocumentLink).all()}
    assert linked == {(ids["docs"]["alpha"], ids["alpha"])}                       # only the deleted well's link
    _scope(widget, "unlinked")                                                     # its document is kept, unlinked
    listed = {widget.table.item(r, 0).data(0x0100) for r in range(widget.table.rowCount())}   # Qt.UserRole
    assert ids["docs"]["twin"] in listed and ids["docs"]["alpha"] not in listed
