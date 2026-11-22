"""M298: schema-driven value-state registry; M299: explicit PER_FIELD batch transaction contract (SYNTHETIC).

The registry must keep the 11 M272 fields (same keys, order and labels) and derive units, bounds and import
support from ``core.canonical_schema`` without inventing any. The batch contract keeps the tested M272 per-field
partial success. Every field is its own transaction (value + state event + audit), so a fault injected into the
audit of one field leaves no row for that field, keeps the other fields saved, and the result says PARTIAL.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy import text  # noqa: E402

from core import canonical_schema  # noqa: E402
from core import ddr_value_states as vs  # noqa: E402
from core.database import AuditLog, DailyReport, DdrValueState  # noqa: E402
from synthetic_operations import build_synthetic_operations, make_file_database  # noqa: E402

M272_FIELDS = ["depth_0000", "depth_0600", "depth_2400", "rop_meter", "wob", "rpm", "torque", "pressure",
               "mud_weight_in", "mud_weight_out", "mw_pcf"]


@pytest.fixture()
def world(tmp_path):
    db = make_file_database(tmp_path / "m299.db")
    ids = build_synthetic_operations(db)
    with db.engine.begin() as conn:
        conn.execute(text("UPDATE daily_reports SET status = 'Draft' WHERE id = :id"), {"id": ids["reports"][1]})
    yield db, ids["reports"][1]
    db.engine.dispose()


# ---- M298 -------------------------------------------------------------------------------------------------------
def test_registry_is_backward_compatible_with_the_eleven_fields():
    registry = vs.field_registry()
    assert list(registry) == list(vs.FIELDS) == M272_FIELDS
    assert all(registry[key].label == vs.FIELDS[key] for key in registry)
    columns = {column.name for column in DailyReport.__table__.columns}
    assert set(registry) <= columns


def test_units_bounds_and_import_support_come_from_the_canonical_schema_only():
    for key, entry in vs.field_registry().items():
        spec = canonical_schema.get_field_spec(f"daily_report.{key}")
        if spec is None:
            assert (entry.unit, entry.import_excel, entry.import_pdf, entry.bounds) == (None, False, False, (None, None))
            assert "no canonical spec" in entry.unit_source
        else:
            assert entry.unit == (spec.unit or None) and entry.import_excel and entry.import_pdf
            assert entry.bounds == canonical_schema.get_engineering_bounds(f"daily_report.{key}")
    registry = vs.field_registry()
    assert registry["depth_2400"].unit == "m" and registry["mw_pcf"].unit == "pcf"
    assert registry["wob"].unit is None                    # never invented


def test_every_entry_carries_the_full_contract():
    for entry in vs.field_registry().values():
        row = entry.as_row()
        assert set(row) == {"key", "label", "unit", "unit_source", "bounds", "states", "missing_contract",
                            "validation", "provenance", "import_excel", "import_pdf", "ui", "persistence"}
        assert row["states"] == list(vs.STATES) and "never 0" in row["missing_contract"]
        assert "comma is refused" in row["validation"]
        assert {"ddr_value_state", "ddr_value_authored", "ddr_import_value_state"} == set(row["provenance"])
        assert row["persistence"].startswith(f"daily_reports.{entry.key} ")
    assert "unit: not declared" in vs.describe("wob") and "Import: not mapped" in vs.describe("wob")
    assert "unit: m" in vs.describe("depth_0000") and "Import: Excel, PDF" in vs.describe("depth_0000")


# ---- M299 -------------------------------------------------------------------------------------------------------
def _rows(db, report):
    with db.session_scope() as session:
        return (session.query(DdrValueState).filter(DdrValueState.report_id == report).count(),
                session.query(AuditLog).filter(AuditLog.action.in_(
                    (vs.AUDIT_ACTION, vs.AUTHORED_AUDIT_ACTION))).count())


def _stored(db, report, field):
    with db.session_scope() as session:
        return getattr(session.get(DailyReport, report), field)


def test_a_clean_batch_saves_every_field(world):
    db, report = world
    result = vs.save_batch(db, report, [{"field": "wob", "typed": "20"}, {"field": "rpm", "state": vs.UNKNOWN},
                                        {"field": "torque", "typed": "0"}])
    assert result.saved == ["wob", "rpm", "torque"] and not result.partial and not result.refused + result.failed
    assert result.message() == "Saved 3 state(s) of 3 change(s)."
    assert (_stored(db, report, "wob"), _stored(db, report, "torque")) == (20.0, 0.0)
    assert vs.states(db, report)["torque"]["state"] == vs.ZERO and _rows(db, report) == (3, 3)


def test_per_field_semantics_with_refusals(world):
    db, report = world
    result = vs.save_batch(db, report, [{"field": "wob", "state": vs.UNKNOWN},
                                        {"field": "depth_2400", "state": vs.UNKNOWN},          # holds 300: refused
                                        {"field": "rpm", "typed": "1,5"},                       # refused
                                        {"field": "torque", "typed": "12.5"}])
    assert result.semantics == vs.PER_FIELD and result.saved == ["wob", "torque"]
    assert [f for f, _r in result.refused] == ["depth_2400", "rpm"] and result.failed == []
    assert result.partial and result.values_changed
    assert "PARTIAL SAVE" in result.message() and "commas are refused" in result.message()
    assert _rows(db, report) == (2, 2) and _stored(db, report, "rpm") is None


def test_an_audit_failure_on_one_field_leaves_no_row_for_it_and_keeps_the_others(world, monkeypatch):
    db, report = world
    original = db._add_mandatory_audit
    calls = {"n": 0}

    def flaky(session, action, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("SYN: audit store unavailable")
        return original(session, action, *args, **kwargs)

    monkeypatch.setattr(db, "_add_mandatory_audit", flaky)
    result = vs.save_batch(db, report, [{"field": "wob", "typed": "20"}, {"field": "rpm", "typed": "120"},
                                        {"field": "torque", "state": vs.NOT_APPLICABLE}])
    assert result.saved == ["wob", "torque"] and [f for f, _r in result.failed] == ["rpm"]
    assert "audit store unavailable" in result.failed[0][1] and result.partial
    assert "NOT SAVED (storage error" in result.message() and "RPM:" in result.message()
    assert _stored(db, report, "wob") == 20.0 and _stored(db, report, "rpm") is None      # no partial row
    assert _rows(db, report) == (2, 2)                                                   # no state without audit
    with db.session_scope() as session:
        assert session.query(DdrValueState).filter_by(report_id=report, field="rpm").count() == 0


def test_a_storage_failure_after_the_state_row_rolls_that_field_back(world, monkeypatch):
    db, report = world
    original = db._add_mandatory_audit

    def failing_for_wob(session, action, entity_type, entity_id=None, entity_name=None, details=""):
        if entity_name == "WOB":
            raise RuntimeError("SYN: disk full")
        return original(session, action, entity_type, entity_id, entity_name, details)

    monkeypatch.setattr(db, "_add_mandatory_audit", failing_for_wob)
    result = vs.save_batch(db, report, [{"field": "wob", "typed": "20"}])
    assert result.saved == [] and not result.partial and [f for f, _r in result.failed] == ["wob"]
    assert _stored(db, report, "wob") is None and _rows(db, report) == (0, 0)


def test_the_dialog_reports_a_partial_save_clearly(world, monkeypatch):
    from PySide6.QtWidgets import QApplication

    from dialogs.ddr_value_states_dialog import DdrValueStatesDialog

    db, report = world
    app = QApplication.instance() or QApplication([])
    original = db._add_mandatory_audit

    def failing_for_rpm(session, action, entity_type, entity_id=None, entity_name=None, details=""):
        if entity_name == "RPM":
            raise RuntimeError("SYN: audit store unavailable")
        return original(session, action, entity_type, entity_id, entity_name, details)

    monkeypatch.setattr(db, "_add_mandatory_audit", failing_for_rpm)
    dialog = DdrValueStatesDialog(db, report)
    try:
        assert "unit: m" in dialog.table.item(dialog.fields.index("depth_0000"), 0).toolTip()
        dialog.set_typed("wob", "20")
        dialog.set_typed("rpm", "120")
        outcome = dialog.save()
        assert outcome["saved"] == ["wob"] and [f for f, _r in outcome["failed"]] == ["rpm"] and outcome["partial"]
        assert "PARTIAL SAVE" in dialog.status.text() and "Saved 1 state(s) of 2" in dialog.status.text()
    finally:
        dialog.deleteLater()
        del app
