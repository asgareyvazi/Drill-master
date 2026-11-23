"""M303–M306: clone contract per adapter, clone provenance, bulk archive / restore, clone vs source (SYNTHETIC).

M303: every ``calculation_history`` adapter has exactly one clone contract; invalid clones are refused with a
reason and write nothing. M304: a clone names its source, copies method and version, is never recalculated or
approved, and detects a source id that was reused (D87 review). M305: bulk archive / restore has a preview, one
reason, per-row status, audit per row, authorization and explicit PER_ROW partial semantics. M306: the clone is
shown next to its source without recalculating either side.
"""
from __future__ import annotations

import dataclasses

import pytest
from sqlalchemy import text

from core import calculation_clone_contract as ccc
from core import calculation_history as ch
from core import calculation_workbench as wb
from core.database import AuditLog, CalculationArchiveMark, CalculationCase
from core.engineering.engines.casing import CasingEngine
from core.repositories.casing_repository import CasingCalculationRepository
from test_m286_workbench_clone_archive import INPUTS, _entry, world  # noqa: F401  (shared SYNTHETIC world)


def _casing(db, dev, label):
    return CasingCalculationRepository(db).save_run(
        inputs=INPUTS, result_values=CasingEngine.evaluate(**INPUTS).values, method=CasingEngine.METHOD,
        label=label, well_id=dev)


def _count(db, model, **where):
    with db.session_scope() as session:
        return session.query(model).filter_by(**where).count()


def _null_created_at(db, table, record_id):
    with db.session_scope() as session:
        session.execute(text(f"UPDATE {table} SET created_at = NULL WHERE id = :i"), {"i": record_id})


# ---- M303 -----------------------------------------------------------------------------------------------------
def test_every_adapter_has_exactly_one_clone_contract():
    tables = [model.__tablename__ for model, _adapt in ch._adapters()]
    assert len(tables) == len(set(tables)) == 11
    assert set(tables) == set(ccc.ADAPTER_MATRIX)
    rows = ccc.adapter_matrix()
    assert [r["table"] for r in rows] == tables and all(r["clone"] == "ALLOWED" for r in rows)
    assert ccc.ADAPTER_MATRIX["survey_revisions"].integrity == "integrity"
    assert ccc.ADAPTER_MATRIX["well_architecture_revisions"].required_inputs == ("components",)


@pytest.mark.parametrize("change, reason", [
    (dict(inputs={}), "no readable inputs"),
    (dict(inputs={"raw": "{not json"}), "unreadable stored inputs"),
    (dict(results={}, full_results={}), "no stored results to copy"),
    (dict(results={"raw": "{not json"}, full_results={}), "unreadable stored results"),
    (dict(table="survey_revisions", inputs={"stations": [{"md": 0}]}, results={"integrity": "HASH MISMATCH"}),
     "failed its integrity check (HASH MISMATCH)"),
    (dict(table="well_architecture_revisions", inputs={"components": []}, results={"integrity": "VERIFIED"}),
     "is missing components"),
    (dict(table="no_such_table"), "has no clone contract"),
])
def test_an_invalid_clone_is_refused_with_a_reason_and_writes_nothing(world, change, reason):  # noqa: F811
    db, dev, casing_id, _case_id = world
    entry = dataclasses.replace(_entry(db, dev, "casing_calculations", casing_id), **change)
    before = _count(db, CalculationCase)
    with pytest.raises(wb.WorkbenchError, match=reason.replace("(", r"\(").replace(")", r"\)")):
        wb.clone(db, entry)
    assert _count(db, CalculationCase) == before
    assert ccc.explain(entry) is not None


def test_a_deleted_source_is_refused(world):  # noqa: F811
    db, dev, casing_id, _case_id = world
    entry = _entry(db, dev, "casing_calculations", casing_id)
    with db.session_scope() as session:
        session.execute(text("DELETE FROM casing_calculations WHERE id = :i"), {"i": casing_id})
    with pytest.raises(wb.WorkbenchError, match="no longer exists"):
        wb.clone(db, entry)


# ---- M304 -----------------------------------------------------------------------------------------------------
def test_clone_provenance_names_the_source_and_what_the_clone_is_not(world):  # noqa: F811
    db, dev, casing_id, case_id = world
    entry = _entry(db, dev, "casing_calculations", casing_id)
    clone = wb.clone(db, entry)
    assert "not approved" in clone["note"] and f"scope {entry.scope}" in clone["note"]
    prov = ccc.clone_provenance(db, clone["id"])
    assert (prov["is_clone"], prov["identity"], prov["recalculated"], prov["approved"]) == \
        (True, ccc.VERIFIED, False, False)
    assert prov["source_key"] == f"casing_calculations:{casing_id}" and prov["method_kept"] is True
    assert prov["source_method"] == CasingEngine.METHOD and prov["verification_status"] == "CLONE"
    assert "NOT recalculated" in ccc.provenance_line(prov) and "NOT approved" in ccc.provenance_line(prov)
    plain = ccc.clone_provenance(db, case_id)
    assert plain["is_clone"] is False and plain["recalculated"] is None and ccc.provenance_line(plain) == "Not a clone."


def test_a_reused_source_id_is_detected_not_trusted(world):  # noqa: F811
    db, dev, casing_id, _case_id = world
    clone = wb.clone(db, _entry(db, dev, "casing_calculations", casing_id))
    with db.session_scope() as session:
        session.execute(text("DELETE FROM casing_calculations WHERE id = :i"), {"i": casing_id})
    assert ccc.clone_provenance(db, clone["id"])["identity"] == ccc.SOURCE_MISSING
    assert _casing(db, dev, "SYN M304 different casing") == casing_id          # SQLite reused the id
    prov = ccc.clone_provenance(db, clone["id"])
    assert prov["identity"] == ccc.SOURCE_REPLACED and "different record" in prov["reason"]
    assert ccc.source_entry(db, prov) is None                                  # never compared with the impostor
    assert ccc.side_by_side(db, clone["id"])["status"] == "SOURCE_NOT_COMPARABLE (SOURCE_REPLACED)"


def test_a_source_without_creation_time_is_content_pinned_since_m365(world):  # noqa: F811
    """M304 refused this archive and reported the clone IDENTITY_WEAK. M365 (D87) pins both by content
    fingerprint, so a NULL created_at no longer leaves identity open (see test_m365_d87_identity.py)."""
    db, dev, casing_id, _case_id = world
    clone = wb.clone(db, _entry(db, dev, "casing_calculations", casing_id))
    _null_created_at(db, "casing_calculations", casing_id)
    prov = ccc.clone_provenance(db, clone["id"])
    assert (prov["identity"], prov["identity_basis"]) == (ccc.VERIFIED, "CONTENT_PINNED")
    entry = _entry(db, dev, "casing_calculations", casing_id)
    marks = _count(db, CalculationArchiveMark)
    assert wb.archive(db, entry, "SYN: superseded")["identity"] == "CONTENT_PINNED"
    assert _count(db, CalculationArchiveMark) == marks + 1 and wb.state(db, entry) == wb.ARCHIVED


def _delete(db, table, record_id):
    with db.session_scope() as session:
        session.execute(text(f"DELETE FROM {table} WHERE id = :i"), {"i": record_id})


# ---- M305 -----------------------------------------------------------------------------------------------------
def _three(db, dev, casing_id):
    second, third = _casing(db, dev, "SYN M305 b"), _casing(db, dev, "SYN M305 c")
    return [_entry(db, dev, "casing_calculations", i) for i in (casing_id, second, third)]


def test_bulk_preview_writes_nothing_and_classifies_every_row(world):  # noqa: F811
    db, dev, casing_id, _case_id = world
    first, second, third = _three(db, dev, casing_id)
    wb.archive(db, first, "SYN: earlier")
    _delete(db, "casing_calculations", third.record_id)          # M365: NULL created_at is no longer a refusal
    marks, audits = _count(db, CalculationArchiveMark), _count(db, AuditLog)
    preview = wb.bulk_preview(db, [first, second, third, second], wb.ARCHIVE)
    assert [(r["key"], r["plan"]) for r in preview["rows"]] == [
        (first.key, wb.SKIP), (second.key, wb.WILL), (third.key, wb.REFUSE), (second.key, wb.SKIP)]
    assert preview["rows"][3]["reason"] == "listed twice in this batch"
    assert preview["counts"] == {wb.WILL: 1, wb.SKIP: 2, wb.REFUSE: 1} and preview["contract"] == "PER_ROW"
    assert (_count(db, CalculationArchiveMark), _count(db, AuditLog)) == (marks, audits)


def test_bulk_apply_is_per_row_with_audit_and_explicit_partial(world):  # noqa: F811
    db, dev, casing_id, _case_id = world
    first, second, third = _three(db, dev, casing_id)
    _delete(db, "casing_calculations", third.record_id)          # M365: NULL created_at is no longer a refusal
    with pytest.raises(wb.WorkbenchError, match="reason is required"):
        wb.bulk_apply(db, [first, second], wb.ARCHIVE, "  ")
    result = wb.bulk_apply(db, [first, second, third], wb.ARCHIVE, "SYN: superseded")
    assert [r["status"] for r in result["rows"]] == [wb.DONE, wb.DONE, wb.REFUSED]
    assert result["partial"] is True and result["message"].startswith("PARTIAL: Archived 2 record(s) (1 refused).")
    for entry in (first, second):
        assert _count(db, AuditLog, action="CALCULATION_ARCHIVE", entity_type="casing_calculations", entity_id=entry.record_id) == 1
    assert _count(db, CalculationArchiveMark, source_id=third.record_id) == 0
    back = wb.bulk_apply(db, [first, second], wb.RESTORE, "SYN: needed again")
    assert back["counts"][wb.DONE] == 2 and back["partial"] is False and "PARTIAL" not in back["message"]


def test_an_audit_fault_on_one_row_leaves_no_mark_for_it_and_keeps_the_others(world, monkeypatch):  # noqa: F811
    db, dev, casing_id, _case_id = world
    first, second, third = _three(db, dev, casing_id)
    real = db._add_mandatory_audit

    def failing(session, action, table, record_id, *args, **kwargs):
        if record_id == second.record_id:
            raise RuntimeError("SYN audit storage fault")
        return real(session, action, table, record_id, *args, **kwargs)

    monkeypatch.setattr(db, "_add_mandatory_audit", failing)
    result = wb.bulk_apply(db, [first, second, third], wb.ARCHIVE, "SYN: superseded")
    assert [r["status"] for r in result["rows"]] == [wb.DONE, wb.FAILED, wb.DONE]
    assert "SYN audit storage fault" in result["rows"][1]["detail"] and result["partial"] is True
    assert "1 NOT SAVED (storage error)" in result["message"]
    assert _count(db, CalculationArchiveMark, source_id=second.record_id) == 0          # rolled back
    assert _count(db, CalculationArchiveMark, source_id=first.record_id) == 1


def test_an_unauthorized_bulk_writes_nothing(world):  # noqa: F811
    db, dev, casing_id, _case_id = world
    entries = _three(db, dev, casing_id)
    marks = _count(db, CalculationArchiveMark)
    state = db._authorization
    principal, enforced = state.principal, state.enforced
    state.principal, state.enforced = None, True                  # the real enforcement path, no principal
    try:
        preview = wb.bulk_preview(db, entries, wb.ARCHIVE)
        assert preview["authorized"] is False and {r["plan"] for r in preview["rows"]} == {wb.REFUSE}
        assert "not authorized" in preview["rows"][0]["reason"]
        with pytest.raises(wb.WorkbenchError, match="refused: not authorized"):
            wb.bulk_apply(db, entries, wb.ARCHIVE, "SYN: superseded")
    finally:
        state.principal, state.enforced = principal, enforced
    assert _count(db, CalculationArchiveMark) == marks


# ---- M305/M306 UI ---------------------------------------------------------------------------------------------
def test_workbench_bulk_archive_clone_refusal_and_clone_vs_source(world):  # noqa: F811
    from PySide6.QtWidgets import QApplication

    from tabs.calculation_history_tab import CalculationHistoryTab

    db, dev, casing_id, _case_id = world
    keys = [e.key for e in _three(db, dev, casing_id)]
    app = QApplication.instance() or QApplication([])
    tab = CalculationHistoryTab(db_manager=db)
    try:
        tab.set_well(dev)

        def row_of(key):
            return next(i for i, e in enumerate(tab.entries) if e.key == key)

        total = tab.total
        tab.select_rows([row_of(k) for k in keys])
        tab._update_actions()
        assert tab.bulk_archive_btn.isEnabled() and not tab.bulk_restore_btn.isEnabled()
        previews = []
        tab.confirm_bulk = lambda preview: previews.append(preview) or None          # cancelled
        assert tab.bulk_set_archived(True) is None and tab.total == total
        assert previews[0]["counts"][wb.WILL] == 3
        tab.confirm_bulk = lambda preview: "SYN bulk obsolete"
        result = tab.bulk_set_archived(True)
        assert result["counts"][wb.DONE] == 3 and tab.total == total - 3
        assert tab.status.text().startswith("Archived 3 record(s).") and keys[0] in tab.status.text()
        tab.show_archived.setChecked(True)                                           # bulk restore, same path
        tab.select_rows([row_of(k) for k in keys])
        tab._update_actions()
        assert tab.bulk_restore_btn.isEnabled() and not tab.bulk_archive_btn.isEnabled()
        tab.confirm_bulk = lambda preview: "SYN bulk needed again"
        assert tab.bulk_set_archived(False)["counts"][wb.DONE] == 3
        tab.show_archived.setChecked(False)
        assert tab.total == total
        # M303: an entry the matrix refuses disables Clone and says why.
        tab.select_rows([0])
        tab.entries[0] = dataclasses.replace(tab.entries[0], inputs={"raw": "x"})
        tab._update_actions()
        assert not tab.clone_btn.isEnabled() and tab.clone_btn.toolTip().startswith("Clone refused:")
        # M306: clone a record, select the clone, open the side-by-side view.
        tab.refresh()
        source_key = next(e.key for e in tab.entries if e.table == "casing_calculations")
        tab.select_rows([row_of(source_key)])
        case = tab.clone_selected()
        tab.select_rows([row_of(f"calculation_cases:{case['id']}")])
        tab._update_actions()
        assert tab.clone_compare_btn.isEnabled()
        tab.clone_compare_btn.click()
        dialog = tab.clone_dialog
        assert dialog is not None and dialog.isVisible() and dialog.objectName() == "clone_comparison_dialog"
        assert dialog.comparison["status"] == "IDENTICAL COPY" and dialog.comparison["rerun"] is False
        assert dialog.fields.rowCount() > 0 and {dialog.fields.item(r, 4).text()
                                                  for r in range(dialog.fields.rowCount())} == {"SAME"}
        assert "not a rerun" in dialog.status_label.text() and "NOT recalculated" in dialog.provenance_label.text()
        assert "copy, not a rerun" in tab.status.text()
        dialog.close()
    finally:
        tab.deleteLater()
        del app
