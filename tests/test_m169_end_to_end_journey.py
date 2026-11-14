"""M169: 20-step end-to-end journey through the real main window for the M147-M160 work.

Real Qt widgets (the M70 window fixture: real MainWindow, real file database, real authorization), the real
DDR pipeline on a COPY of the synthetic golden workbook (its SHA-256 is checked at the end), the persisted review
queue, the CONTEXT_BLOCKED auto-save path and the tubular reference library. SYNTHETIC data only.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import warnings
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from test_m70_selection_audit import _pump, window  # noqa: E402,F401

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_ddr_golden_a.xlsx"


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _tab(win, name):
    return next(win.tab_widget.widget(i) for i in range(win.tab_widget.count())
                if type(win.tab_widget.widget(i)).__name__ == name)


def test_m169_twenty_step_journey(window, tmp_path, caplog):  # noqa: F811
    from core import ddr_import_pipeline as pipe
    from core.database import AuditLog, TimeLog24H
    from core.ddr_continuation import DEFERRED_UNRESOLVED, SAFELY_ATTACHED_CONTINUATION
    from core.ddr_import_service import DDRImportService
    from core.engineering import tubular_reference as tr
    from core.import_quality import apply_review_decisions
    from core.import_router import route_file
    from core.managers import AutoSaveManager
    from core.selection_manager import SelectionManager
    from core.workbook_io import DATA_VALIDATION_NOTICE, load_workbook_readonly_safe
    from dialogs.excel_import_dialog import has_meaningful_canonical_data
    from dialogs.import_review_dialog import ImportReviewDialog
    from dialogs.tubular_reference_dialog import TubularReferenceDialog

    win, db, ids = window
    well = ids["alpha"]

    # 1. The real window offers the review queue and the tubular library.
    actions = [a.text() for m in win.menuBar().findChildren(type(win.menuBar().actions()[0].menu()))
               for a in m.actions()]
    assert any("Import Review Queue" in t for t in actions) and any("Tubular Reference Library" in t for t in actions)

    # 2. A copy of the synthetic workbook; its fingerprint is recorded.
    source = tmp_path / "journey.xlsx"
    shutil.copyfile(FIXTURE, source)
    before = _sha(source)

    # 3. Real pipeline: version 2 and the three 24-hour continuation proposals with proven parents.
    service = DDRImportService()
    out = pipe.prepare_import(str(source), route=route_file, template_matcher=service._auto_match_template,
                              extract_file=service.extract_file, meaningful=has_meaningful_canonical_data)
    assert out.import_report["pipeline_version"] == 2
    continuations = [r for r in out.import_report["review"] if r.get("review_type") == "continuation"]
    day = [r for r in continuations if r["detected_table"] == "time_logs_24h"]
    assert [r["parent"]["row"] for r in day] == [24, 27, 32] and all(r["eligible"] for r in day)

    # 4. The user attaches one proposal and leaves the rest open (explicit partial import).
    day[0]["decision"] = "ATTACH_CONTINUATION"
    extracted = out.extracted
    apply_review_decisions(extracted, out.import_report["review"])
    result = DDRImportService(db, well).import_records(extracted)
    assert result["report_id"], result
    report_id = result["report_id"]
    with db.session_scope() as session:
        from core.database import DailyReport
        well = session.get(DailyReport, report_id).well_id       # the import files under the workbook's well

    # 5. Truthful outcome: one attached; every undecided row (continuations AND scalar reviews) retained.
    queue = result["review_queue"]
    undecided = len(out.import_report["review"]) - 1
    assert queue["attached"] == 1 and queue["pending"] == undecided and queue["total"] == undecided + 1

    # 6. Seven time logs; only the attached parent carries a line break.
    with db.session_scope() as session:
        texts = [r.activity_description for r in
                 session.query(TimeLog24H).filter_by(report_id=report_id).order_by(TimeLog24H.id)]
    assert len(texts) == 7 and sum("\n" in t for t in texts) == 1 and "\n" in texts[0]

    # 7. The persisted queue holds every proposal with its state.
    items = db.get_import_review_items(well, report_id=report_id)
    assert len([i for i in items if i["state"] == DEFERRED_UNRESOLVED]) == undecided     # persisted, not just counted
    states = sorted(i["state"] for i in items if i["review_type"] == "continuation")
    assert states.count(SAFELY_ATTACHED_CONTINUATION) == 1
    assert states.count(DEFERRED_UNRESOLVED) == len(continuations) - 1

    # 8. The review workspace (real dialog) shows the open items.
    dialog = ImportReviewDialog(db, well, win, report_id=report_id)
    _pump(0.1)
    assert dialog.table.rowCount() == undecided
    dialog.close()

    # 9. A deferred eligible 24-hour continuation is attached later through the audited operation.
    pending = [i for i in items if i["state"] == DEFERRED_UNRESOLVED and i["eligible"]
               and i.get("detected_table", "time_logs_24h") == "time_logs_24h"]
    attached = db.resolve_import_review_item(pending[0]["id"], well, "ATTACH_CONTINUATION")
    assert attached["state"] == SAFELY_ATTACHED_CONTINUATION
    with db.session_scope() as session:
        texts = [r.activity_description for r in session.query(TimeLog24H).filter_by(report_id=report_id)]
    assert sum("\n" in t for t in texts) == 2 and len(texts) == 7

    # 10. Another one is rejected; a decided item is never decided again.
    rejected = db.resolve_import_review_item(pending[1]["id"], well, "REJECT")
    assert rejected["state"] == "REJECTED"
    with pytest.raises(ValueError, match="already decided"):
        db.resolve_import_review_item(pending[1]["id"], well, "ATTACH_CONTINUATION")

    # 11. A foreign well cannot decide this well's item.
    other = next(w for w in (ids["alpha"], ids["twin_1"]) if w != well)
    with pytest.raises((ValueError, PermissionError)):
        db.resolve_import_review_item(pending[-1]["id"], other, "IGNORE")
    assert [i["state"] for i in db.get_import_review_items(well) if i["id"] == pending[-1]["id"]] == [
        DEFERRED_UNRESOLVED]

    # 12. Every decision is audited.
    with db.session_scope() as session:
        assert session.query(AuditLog).filter_by(action="ddr_review_decision").count() >= 2

    # 13. The source workbook was never modified.
    assert _sha(source) == before

    # 14. A selection change reaches the hidden Daily Report tab as a pending context.
    daily = _tab(win, "DailyReportWidget")
    win.tab_widget.setCurrentIndex(0)
    _pump(0.1)
    manager = SelectionManager()
    manager.select_well(other, {"name": "other"}, force=True)
    _pump(0.2)
    assert not daily.isVisible() and not daily.save_context_ready()
    assert "not loaded yet" in daily.context_block_reason()

    # 15. Its timer tick saves nothing and raises no CONTEXT_BLOCKED warning (no edits were held back).
    with caplog.at_level(logging.DEBUG, logger="core.managers"):
        outcome = AutoSaveManager.save_widget("Daily Report", daily)
    assert outcome.disposition == "NO_CHANGES"
    assert not [r for r in caplog.records if r.levelname == "WARNING" and "CONTEXT_BLOCKED" in r.getMessage()]

    # 16. Opening the tab loads the pending context.
    win.tab_widget.setCurrentWidget(daily)
    _pump(0.3)
    assert daily.save_context_ready()

    # 17. A user library version is built and published (no shipped pipe data).
    user = tr.Provenance(origin="user", entered_by="journey")
    v1 = tr.create_set(db, "SYN journey library")
    tr.add_item(db, v1["id"], tr.TubularSpec(component_type="DP", designation="SYN-DP-J", provenance=user,
                                             nominal_od_in=5.0, id_in=4.276))
    tr.publish_set(db, v1["id"])

    # 18. The real search dialog cites the published item as an immutable snapshot; weight stays unavailable.
    picker = TubularReferenceDialog(db, win, component_type="DP")
    picker.table.selectRow(0)
    picker._use_selected()
    snapshot = picker.selected_snapshot
    assert snapshot["set_version"] == 1 and snapshot["spec"]["weight_ppf"] is None
    picker.close()

    # 19. A later revision is reported as drift; the snapshot keeps citing v1 and still verifies.
    v2 = tr.create_set(db, "SYN journey library")
    tr.add_item(db, v2["id"], tr.TubularSpec(component_type="HWDP", designation="SYN-HW-J", provenance=user))
    tr.publish_set(db, v2["id"])
    assert "newer published version" in tr.snapshot_drift(db, snapshot) and tr.verify_snapshot(snapshot) == []

    # 20. Opening the workbook again explains the data-validation notice and still leaves it untouched.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        book = load_workbook_readonly_safe(source, data_only=True)
    book.close()
    assert book.drillmaster_notices == [DATA_VALIDATION_NOTICE]
    assert not [w for w in caught if "Data Validation extension" in str(w.message)]
    assert _sha(source) == before
