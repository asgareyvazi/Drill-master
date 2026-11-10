"""M157-M160: typed, versioned tubular reference library; immutable snapshots; search UI; workbook warnings.

Every number below is SYNTHETIC test input (designations ``SYN-*``) - the application ships no pipe rows.
Fresh isolated databases, real Qt widgets.
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import warnings
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.engineering import tubular_reference as tr  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_ddr_golden_a.xlsx"
USER = tr.Provenance(origin="user", entered_by="synthetic-tester", units="in, lb/ft, psi")


def _spec(designation="SYN-DP-A", **values):
    base = dict(component_type="DP", designation=designation, provenance=USER, nominal_od_in=5.0, id_in=4.276,
                weight_ppf=19.5, grade="SYN-G", connection="SYN-C")
    base.update(values)
    return tr.TubularSpec(**base)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def db(tmp_path):
    from core.database import DatabaseManager
    manager = DatabaseManager()
    manager.db_path = str(tmp_path / "tubular.db")
    manager.initialize()
    return manager


# ------------------------------------------------------------------------------ M157 contract

def test_m157_every_component_type_is_typed_and_unknown_types_refused():
    assert tr.COMPONENT_TYPES == ("DP", "HWDP", "DC", "TOOL_JOINT", "CASING", "TUBING", "LINER")
    for code in tr.COMPONENT_TYPES:
        assert tr.validate_spec(_spec(component_type=code)) == []
    assert "Unknown component type" in tr.validate_spec(_spec(component_type="PIPE"))[0]


def test_m157_missing_values_stay_unavailable_never_zero():
    spec = _spec(id_in=None, weight_ppf=None)
    assert tr.validate_spec(spec) == []
    assert spec.display_value("id_in") == "unavailable" and spec.display_value("weight_ppf") == "unavailable"
    assert "id_in" in spec.unavailable_fields() and "burst_psi" in spec.unavailable_fields()
    assert tr.TubularSpec.from_payload(spec.to_payload()) == spec            # lossless; None survives


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf"), True, "5"])
def test_m157_non_positive_or_non_numeric_values_are_refused(bad):
    assert any("positive number" in issue for issue in tr.validate_spec(_spec(burst_psi=bad)))


def test_m158_manufacturer_entries_need_document_and_explicit_licence():
    no_licence = tr.Provenance(origin="manufacturer", manufacturer="SYN Maker", document="SYN catalogue",
                               url="https://example.invalid/catalogue")
    issues = tr.validate_spec(_spec(provenance=no_licence))
    assert any("licence" in issue and "public page is not a redistribution licence" in issue for issue in issues)
    licensed = replace(no_licence, licence="SYN written permission", revision="r1", page="12")
    assert tr.validate_spec(_spec(provenance=licensed)) == []


def test_m158_derived_entries_must_state_the_derivation_and_origins_never_mix():
    assert "derived_from" in tr.validate_spec(_spec(provenance=tr.Provenance(origin="derived")))[0]
    assert "Unknown origin" in tr.validate_spec(_spec(provenance=tr.Provenance(origin="vendor-ish")))[0]
    base = _spec()
    derived = tr.derive_wall(base)
    assert derived.provenance.origin == "derived" and base.fingerprint()[:12] in derived.provenance.derived_from
    assert math.isclose(derived.wall_in, (5.0 - 4.276) / 2) and base.wall_in is None     # source untouched
    assert tr.derive_wall(_spec(id_in=None)) is None                                       # never invented


def test_m157_geometry_contradictions_are_refused():
    assert "ID must be smaller" in tr.validate_spec(_spec(id_in=5.5))[0]
    assert "Drift cannot exceed" in tr.validate_spec(_spec(drift_in=4.5))[0]
    assert "Wall thickness contradicts" in tr.validate_spec(_spec(wall_in=0.5))[0]
    assert tr.validate_spec(_spec(wall_in=0.362)) == []
    assert "Tool joint ID" in tr.validate_spec(_spec(tool_joint_od_in=6.0, tool_joint_id_in=6.5))[0]


# ------------------------------------------------------------------------- versioning (real DB)

def test_m157_published_sets_are_immutable_and_revisions_are_new_versions(db):
    v1 = tr.create_set(db, "SYN library")
    assert tr.add_item(db, v1["id"], _spec())["status"] == "NEW"
    assert tr.add_item(db, v1["id"], _spec())["status"] == "UNCHANGED"              # idempotent
    with pytest.raises(tr.TubularReferenceError, match="still a draft"):
        tr.create_set(db, "SYN library")
    published = tr.publish_set(db, v1["id"])
    with pytest.raises(tr.TubularReferenceError, match="immutable"):
        tr.add_item(db, v1["id"], _spec("SYN-DP-B"))
    with pytest.raises(tr.TubularReferenceError, match="immutable"):
        tr.remove_item(db, v1["id"], _spec().fingerprint())
    with pytest.raises(tr.TubularReferenceError, match="already published"):
        tr.publish_set(db, v1["id"])
    v2 = tr.create_set(db, "SYN library")
    assert v2["version"] == 2
    tr.add_item(db, v2["id"], _spec("SYN-HW-A", component_type="HWDP", nominal_od_in=5.0, id_in=3.0))
    assert tr.remove_item(db, v2["id"], _spec().fingerprint()) is True
    tr.publish_set(db, v2["id"])
    sets = {s["version"]: s for s in tr.list_sets(db)}
    assert sets[1]["items"] == 1 and sets[1]["fingerprint"] == published["fingerprint"]   # v1 unchanged
    assert sets[2]["items"] == 1


def test_m157_empty_set_cannot_be_published_and_invalid_specs_never_stored(db):
    ref = tr.create_set(db, "SYN empty")
    with pytest.raises(tr.TubularReferenceError, match="empty"):
        tr.publish_set(db, ref["id"])
    with pytest.raises(tr.TubularReferenceError, match="ID must be smaller"):
        tr.add_item(db, ref["id"], _spec(id_in=9.0))
    assert tr.list_sets(db)[0]["items"] == 0


def test_m159_search_filters_and_hides_drafts(db):
    ref = tr.create_set(db, "SYN search")
    tr.add_item(db, ref["id"], _spec())
    tr.add_item(db, ref["id"], _spec("SYN-CSG-A", component_type="CASING", nominal_od_in=9.625, id_in=8.681,
                                     grade="SYN-L", connection="SYN-BT"))
    assert tr.search(db) == []                                                    # draft hidden by default
    assert len(tr.search(db, published_only=False)) == 2
    tr.publish_set(db, ref["id"])
    assert [r["spec"].designation for r in tr.search(db, component_type="CASING")] == ["SYN-CSG-A"]
    assert [r["spec"].designation for r in tr.search(db, od_in=5.0)] == ["SYN-DP-A"]
    assert [r["spec"].designation for r in tr.search(db, text="syn-bt")] == ["SYN-CSG-A"]
    assert tr.search(db, origin="manufacturer") == []


# ------------------------------------------------------------------------------- snapshots

def test_m159_snapshots_are_immutable_self_contained_and_detect_tampering(db):
    ref = tr.create_set(db, "SYN snap")
    tr.add_item(db, ref["id"], _spec())
    [draft_row] = tr.search(db, published_only=False)
    with pytest.raises(tr.TubularReferenceError, match="published"):
        tr.reference_snapshot(draft_row)
    tr.publish_set(db, ref["id"])
    [row] = tr.search(db)
    snapshot = tr.reference_snapshot(row)
    assert snapshot["set_version"] == 1 and tr.verify_snapshot(snapshot) == []
    assert tr.snapshot_drift(db, snapshot) is None
    v2 = tr.create_set(db, "SYN snap")
    tr.add_item(db, v2["id"], _spec("SYN-DP-B"))
    tr.publish_set(db, v2["id"])
    assert "1 newer published version" in tr.snapshot_drift(db, snapshot)      # reported, never rewritten
    assert tr.verify_snapshot(snapshot) == [] and snapshot["spec"]["designation"] == "SYN-DP-A"
    tampered = dict(snapshot, spec=dict(snapshot["spec"], weight_ppf=25.6))
    assert tr.verify_snapshot(tampered)
    relabelled = dict(snapshot, set_version=9)                  # only the snapshot fingerprint can catch this
    assert tr.verify_snapshot(relabelled) == ["Snapshot content does not match its fingerprint "
                                              "(modified after it was stored)"]


# ------------------------------------------------------------------------------- dialog (Qt)

def test_m159_dialog_filters_shows_unavailable_and_only_cites_published_items(db, qapp):
    from dialogs.tubular_reference_dialog import COLUMNS, TubularReferenceDialog
    published = tr.create_set(db, "SYN ui")
    tr.add_item(db, published["id"], _spec(weight_ppf=None))
    tr.add_item(db, published["id"], _spec("SYN-DC-A", component_type="DC", nominal_od_in=6.5, id_in=2.8125))
    tr.publish_set(db, published["id"])
    draft = tr.create_set(db, "SYN draft")
    tr.add_item(db, draft["id"], _spec("SYN-TB-A", component_type="TUBING", nominal_od_in=3.5, id_in=2.992))
    dialog = TubularReferenceDialog(db, component_type="DP")
    assert dialog.table.rowCount() == 1
    weight_col = [key for key, _ in COLUMNS].index("weight_ppf")
    assert dialog.table.item(0, weight_col).text() == "unavailable"
    dialog.table.selectRow(0)
    assert "licence: unavailable" in dialog.detail.toPlainText()
    dialog._use_selected()
    assert dialog.selected_snapshot["spec"]["designation"] == "SYN-DP-A"
    assert dialog.selected_snapshot["spec"]["weight_ppf"] is None
    dialog.selected_snapshot = None
    dialog.type_combo.setCurrentIndex(tr.COMPONENT_TYPES.index("TUBING") + 1)
    dialog.drafts_check.setChecked(True)
    assert dialog.table.rowCount() == 1
    dialog.table.selectRow(0)
    dialog._use_selected()
    assert dialog.selected_snapshot is None and "published" in dialog.status.text()
    dialog.close()


def test_m159_empty_library_says_no_data_is_shipped(db, qapp):
    from dialogs.tubular_reference_dialog import TubularReferenceDialog
    dialog = TubularReferenceDialog(db)
    assert dialog.table.rowCount() == 0 and "ships no pipe data" in dialog.status.text()
    dialog.close()


# ------------------------------------------------------------------------ M160 workbook warnings

def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_m160_data_validation_warning_is_explained_and_the_workbook_untouched(caplog):
    from core.workbook_io import DATA_VALIDATION_NOTICE, load_workbook_readonly_safe
    with warnings.catch_warnings(record=True) as raw:
        warnings.simplefilter("always")
        from openpyxl import load_workbook
        load_workbook(FIXTURE, data_only=True).close()
    assert any("Data Validation extension" in str(w.message) for w in raw), "fixture must reproduce the warning"
    before = _sha(FIXTURE)
    with caplog.at_level(logging.INFO, logger="core.workbook_io"), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        workbook = load_workbook_readonly_safe(FIXTURE, data_only=True)
    assert not [w for w in caught if "Data Validation extension" in str(w.message)]
    assert workbook.drillmaster_notices == [DATA_VALIDATION_NOTICE]
    assert "DDR Remark" in workbook.sheetnames
    workbook.close()
    assert [r.levelname for r in caplog.records if DATA_VALIDATION_NOTICE in r.getMessage()] == ["INFO"]
    assert _sha(FIXTURE) == before


def test_m160_other_warnings_are_not_swallowed(monkeypatch):
    import openpyxl
    from core.workbook_io import load_workbook_readonly_safe

    def fake(path, **kwargs):
        warnings.warn("Data Validation extension is not supported and will be removed", UserWarning)
        warnings.warn("synthetic unrelated warning", UserWarning)
        return type("WB", (), {})()
    monkeypatch.setattr(openpyxl, "load_workbook", fake)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        load_workbook_readonly_safe("synthetic.xlsx")
    assert [str(w.message) for w in caught] == ["synthetic unrelated warning"]


def test_m160_absent_optional_drillpipe_file_is_info_not_warning(monkeypatch, caplog, tmp_path):
    import core.runtime_config as runtime_config
    from tabs.w13_Engineering_Calculator import EngineeringCalculatorTab
    monkeypatch.setattr(runtime_config, "drill_pipe_reference_paths", lambda: [tmp_path / "DrillPipe.xlsx"])
    holder = type("Holder", (), {"_drill_pipe_df": None})()
    with caplog.at_level(logging.INFO, logger="tabs.w13_Engineering_Calculator"):
        EngineeringCalculatorTab._load_drill_pipe_db(holder)
    records = [r for r in caplog.records if "DrillPipe vendor reference unavailable" in r.getMessage()]
    assert [r.levelname for r in records] == ["INFO"] and holder._drill_pipe_df is None
    broken = tmp_path / "Broken.xlsx"
    broken.write_bytes(b"not a workbook")
    monkeypatch.setattr(runtime_config, "drill_pipe_reference_paths", lambda: [broken])
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="tabs.w13_Engineering_Calculator"):
        EngineeringCalculatorTab._load_drill_pipe_db(holder)
    assert any(r.levelname == "WARNING" and "Could not load DrillPipe.xlsx" in r.getMessage() for r in caplog.records)
    assert broken.read_bytes() == b"not a workbook"
