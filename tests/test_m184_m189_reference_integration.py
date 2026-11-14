"""M184-M189: the tubular reference library in Architecture, Volumes, Hydraulics, Weight / T&D and Casing strength,
through one shared binding service (``tubular-binding-v1``) with snapshot drift MATCH / DIFFERENT /
NOT_REPRODUCIBLE / UNREADABLE.

Every library item is SYNTHETIC (``SYN-*``, deliberately non-catalogue numbers); no pipe data ships. Real Qt
widgets, real SQLite files in tmp_path (fresh, and reopened from disk for the persistence checks). The M126 /
M127 goldens are unchanged: a library pick only fills inputs, it never changes the method.
"""
from __future__ import annotations

import json
import math
import os

import pytest
from sqlalchemy import text

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6 import QtWidgets  # noqa: E402

from core import calculation_history as ch  # noqa: E402
from core import well_architecture as wa  # noqa: E402
from core.engineering import reference_binding as rb  # noqa: E402
from core.engineering import tubular_reference as tr  # noqa: E402
from tests.test_m70_integrity import _open, _seed  # noqa: E402
from tests.test_m74_well_architecture import ARCH  # noqa: E402

PROV = tr.Provenance(origin="user", entered_by="synthetic-tester", document="SYN sheet")
ITEMS = [
    tr.TubularSpec("DP", "SYN-DP-48", PROV, grade="SYN-G", connection="SYN-C", nominal_od_in=4.871, id_in=4.013,
                   weight_ppf=18.7, tool_joint_od_in=6.37),
    tr.TubularSpec("DP", "SYN-DP-NOID", PROV, nominal_od_in=3.911, weight_ppf=12.9),
    tr.TubularSpec("CASING", "SYN-CSG-96", PROV, grade="SYN-80", nominal_od_in=9.611, id_in=8.703, wall_in=0.454,
                   weight_ppf=46.1),
    tr.TubularSpec("CASING", "SYN-CSG-NOID", PROV, nominal_od_in=7.013),
    tr.TubularSpec("CASING", "SYN-CSG-NOWALL", PROV, nominal_od_in=7.011, id_in=6.183),
]


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def env(tmp_path, monkeypatch):
    manager = _open(tmp_path / "m184.sqlite", tmp_path, monkeypatch)
    ids = _seed(manager)
    set_id = tr.create_set(manager, "SYN library")["id"]
    for spec in ITEMS:
        tr.add_item(manager, set_id, spec)
    tr.publish_set(manager, set_id)
    yield manager, ids, tmp_path / "m184.sqlite"
    manager.close()


@pytest.fixture
def w13(app, env, monkeypatch):
    from PySide6.QtCore import QCoreApplication, QEvent

    from tabs import w13_Engineering_Calculator as w13_module
    manager, ids, _path = env
    monkeypatch.setattr(w13_module.QMessageBox, "information", lambda *a, **k: None)
    tab = w13_module.EngineeringCalculatorTab(manager)
    tab.on_well_changed(ids["A"][0], {"name": "SYN-A"})
    yield tab
    tab.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def snap(db, designation):
    row = next(r for r in tr.search(db) if r["spec"].designation == designation)
    return tr.reference_snapshot(row)


def _value(case, field_id):
    return next(v["value"] for v in case["results"].values() if isinstance(v, dict) and v.get("field_id") == field_id)


def _entry(db, case_id):
    return next(e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == case_id)


# ------------------------------------------------------------------------------ M189 shared service

def test_binding_fills_only_available_values_and_refuses_a_damaged_snapshot(env):
    db = env[0]
    full = rb.make_binding(snap(db, "SYN-DP-48"), rb.PIPE_COMPONENT_FIELDS)
    assert rb.bound_values(full) == {"od": 4.871, "id": 4.013, "weight": 18.7, "grade": "SYN-G",
                                     "connection": "SYN-C", "tj_od": 6.37} and full["unavailable"] == []
    partial = rb.make_binding(snap(db, "SYN-DP-NOID"), rb.PIPE_COMPONENT_FIELDS)
    assert set(partial["unavailable"]) == {"id", "grade", "connection", "tj_od"}
    assert "id" not in partial["fields"]                                   # never filled, never 0
    tampered = snap(db, "SYN-DP-48")
    tampered["spec"]["nominal_od_in"] = 5.5
    with pytest.raises(rb.BindingError, match="not intact"):
        rb.make_binding(tampered, rb.PIPE_COMPONENT_FIELDS)
    empty = snap(db, "SYN-CSG-NOID")
    with pytest.raises(rb.BindingError, match="none of the values"):
        rb.make_binding(empty, {"x": "drift_in"})


def test_an_edited_value_detaches_the_binding_and_absent_keys_are_not_compared(env):
    binding = rb.make_binding(snap(env[0], "SYN-DP-48"), rb.PIPE_COMPONENT_FIELDS)
    row = {"od": 4.871, "id": 4.013, "length": 100.0, "weight": 18.7}           # hydraulics row: no grade column
    assert rb.binding_holds(binding, row) and rb.attach(row, binding)[rb.BINDING_KEY] == binding
    assert rb.edited_fields(binding, dict(row, od=4.88)) == ["od"]
    assert rb.BINDING_KEY not in rb.attach(dict(row, od=4.88), binding)
    assert rb.BINDING_KEY not in rb.attach(dict(row, id=None), binding)        # a cleared value is an edit
    assert not rb.binding_holds({"contract": "other", **binding} | {"contract": "other"}, row)
    assert rb.attach(row, None) == row


def test_drift_states_match_different_not_reproducible_and_unreadable(env, tmp_path, monkeypatch):
    db = env[0]
    snapshot = snap(db, "SYN-DP-48")
    assert rb.drift(db, snapshot).state == rb.MATCH
    revision = tr.create_set(db, "SYN library")["id"]                     # v2 copies v1, then changes
    tr.remove_item(db, revision, snapshot["item_fingerprint"])
    tr.publish_set(db, revision)
    state = rb.drift(db, snapshot)
    assert state.state == rb.MATCH and "1 newer published version(s) exist and are NOT applied" in state.message
    tampered = json.loads(json.dumps(snapshot))
    tampered["spec"]["weight_ppf"] = 99.0
    assert rb.drift(db, tampered).state == rb.UNREADABLE
    assert rb.drift(db, None).state == rb.UNREADABLE
    other = _open(tmp_path / "other.sqlite", tmp_path, monkeypatch)
    try:
        assert rb.drift(other, snapshot).state == rb.NOT_REPRODUCIBLE        # the snapshot stays valid
        assert tr.verify_snapshot(snapshot) == []
    finally:
        other.close()
    with db.session_scope() as session:                                    # the storage guard refuses it ...
        with pytest.raises(Exception, match="published reference set is immutable"):
            session.execute(text("UPDATE tubular_reference_sets SET content_fingerprint = 'x' WHERE version = 1"))
    with db.session_scope() as session:                     # ... file-level access can drop it (documented limit)
        session.execute(text("DROP TRIGGER trg_tubular_set_frozen_v1"))
        session.execute(text("UPDATE tubular_reference_sets SET content_fingerprint = 'x' WHERE version = 1"))
    assert rb.drift(db, snapshot).state == rb.DIFFERENT
    report = rb.drift_report(db, {"a": [{"tubular_reference": rb.make_binding(snapshot, {"od": "nominal_od_in"})}]})
    assert report[0]["path"] == "/a/0/tubular_reference" and report[0]["state"] == rb.DIFFERENT
    assert rb.summarize(report) == "Library references: 1 DIFFERENT" and rb.summarize([]) == ""


# ----------------------------------------------------------------- string component dialog (M185-M187)

def test_pipe_dialog_fills_from_the_library_and_keeps_the_binding_only_while_unchanged(app, env):
    from dialogs.engineering_dialogs import AddPipeDialog

    db = env[0]
    dialog = AddPipeDialog(None, tubular_db=db)
    try:
        assert dialog.library_btn.isEnabled()
        assert dialog.apply_library_snapshot(snap(db, "SYN-DP-48"))
        assert (dialog.od.value(), dialog.id_.value(), dialog.weight.value(), dialog.tj_od.value()) == \
            (4.871, 4.013, 18.7, 6.37)
        assert dialog.type_combo.currentText() == "Drill Pipe" and dialog.grade.currentText() == "SYN-G"
        assert "SYN-DP-48 (SYN library v1)" in dialog.library_label.text()
        dialog.length.setValue(950.0)
        dialog._save()
        result = dialog.result
        assert result[rb.BINDING_KEY]["snapshot"]["spec"]["designation"] == "SYN-DP-48"
    finally:
        dialog.deleteLater()
    reopened = AddPipeDialog(None, edit_data=result, tubular_db=db)
    try:
        assert "SYN-DP-48" in reopened.library_label.text()
        reopened._save()
        assert reopened.result[rb.BINDING_KEY] == result[rb.BINDING_KEY]
    finally:
        reopened.deleteLater()
    edited = AddPipeDialog(None, edit_data=result, tubular_db=db)
    try:
        edited.od.setValue(4.9)
        edited._save()
        assert rb.BINDING_KEY not in edited.result and edited.result["od"] == 4.9
    finally:
        edited.deleteLater()


def test_pipe_dialog_leaves_unavailable_values_unknown_and_refuses_a_tampered_item(app, env):
    from dialogs.engineering_dialogs import AddPipeDialog

    db = env[0]
    dialog = AddPipeDialog(None, tubular_db=db)
    try:
        dialog.id_.setValue(2.5)                                      # stale value from before the pick
        assert dialog.apply_library_snapshot(snap(db, "SYN-DP-NOID"))
        assert dialog.id_.value() == 0.0 and "Unavailable in the library: id" in dialog.library_label.text()
        dialog.length.setValue(10.0)
        dialog._save()
        assert dialog.result is None or dialog.result == {}           # ID required: nothing is guessed
        dialog.id_.setValue(3.1)                                      # the user enters the measured ID
        dialog._save()
        assert dialog.result["id"] == 3.1 and rb.BINDING_KEY in dialog.result
        assert "id" not in dialog.result[rb.BINDING_KEY]["fields"]
        bad = snap(db, "SYN-DP-48")
        bad["snapshot_fingerprint"] = "0" * 64
        assert not dialog.apply_library_snapshot(bad) and "NOT USED" in dialog.library_label.text()
    finally:
        dialog.deleteLater()
    assert not AddPipeDialog(None).library_btn.isEnabled()           # no database: no library


def _library_pipe(db, length):
    binding = rb.make_binding(snap(db, "SYN-DP-48"), rb.PIPE_COMPONENT_FIELDS)
    row = {"type": "Drill Pipe", "od": 4.871, "id": 4.013, "length": length, "weight": 18.7, "grade": "SYN-G",
           "connection": "SYN-C", "tj_od": 6.37}
    return rb.attach(row, binding)


# ------------------------------------------------------------------------------------- M185 Volumes

def test_volumes_case_stores_the_snapshot_keeps_the_golden_and_reports_drift_on_reopen(w13, env):
    db = env[0]
    assert w13.calculator_finder.open_path("Volume › Well Volumes")
    pumps = [{"name": "SYN P1", "output_bbl_stk": 0.1, "spm": 100.0}]
    bores = [{"type": "SYN casing", "od": 9.611, "id": 8.703, "from": 0.0, "to": 1000.0},
             {"type": "Open Hole", "od": 8.5, "id": 8.5, "from": 1000.0, "to": 3000.0}]
    plain = [{"type": "Drill Pipe", "od": 4.871, "id": 4.013, "length": 3000.0}]
    w13.vol_pumps[:], w13.vol_pipes[:], w13.vol_casings[:] = pumps, [dict(p) for p in plain], bores
    w13._vol_refresh_pump_table(), w13._vol_refresh_pipe_table(), w13._vol_refresh_csg_table()
    w13.vol_depth.setValue(3000.0)
    w13._vol_calculate()
    baseline = dict(w13.vol_assessment["results"])
    w13.vol_pipes[:] = [_library_pipe(db, 3000.0)]
    w13._vol_refresh_pipe_table()
    w13._vol_calculate()
    assert w13.vol_assessment["results"] == baseline                       # the method is unchanged
    string_bbl = 4.013 ** 2 / 1029.4 * 3000.0 * 3.28084                    # closed form, ID^2/1029.4 bbl/ft
    assert baseline["string_volume_bbl"] == pytest.approx(string_bbl, rel=1e-9)
    case = w13.case_bar.save_case("SYN volumes from the library")
    assert case["method_version"] == "M126 well volumes v1"
    stored = case["inputs"]["extra:pipes"]["value"][0][rb.BINDING_KEY]
    assert tr.verify_snapshot(stored["snapshot"]) == []
    assert ch.recalculate_entry(_entry(db, case["id"]))["status"] == "MATCH"
    w13.vol_pipes[:] = []
    assert w13.case_bar.reopen(case["id"]) == []
    assert w13.vol_pipes[0][rb.BINDING_KEY] == stored
    assert "Library references: 1 MATCH" in w13.case_bar.status.text()


# ---------------------------------------------------------------------------------- M186 Hydraulics

def test_hydraulics_rows_carry_the_binding_and_drop_it_when_a_cell_is_edited(w13, env):
    db = env[0]
    assert w13.calculator_finder.open_path("Hydraulics")
    w13.hy_pipe_rows = [_library_pipe(db, 2800.0), {"type": "DC", "od": 6.5, "id": 2.8125, "length": 200.0,
                                                    "weight": 92.0}]
    rows = w13.hy_pipe_rows
    assert rows[0][rb.BINDING_KEY]["snapshot"]["spec"]["designation"] == "SYN-DP-48"
    assert rb.BINDING_KEY not in rows[1]
    assert set(rows[0]) == {"type", "od", "id", "length", "weight", rb.BINDING_KEY}   # grade is not a column
    w13.hy_pipe_table.setItem(0, 1, w13._hy_value_item(4.9, ".3f"))             # the user edits the OD
    assert rb.BINDING_KEY not in w13.hy_pipe_rows[0]


def test_hydraulics_results_are_identical_with_and_without_the_binding(w13, env):
    db = env[0]
    assert w13.calculator_finder.open_path("Hydraulics")

    def run(pipes):
        w13.hy_pumps[:] = [{"name": "SYN P1", "output_bbl_stk": 0.1, "spm": 100.0}]
        w13._hy_refresh_pump_table()
        w13.hy_pipe_rows = pipes
        w13.hy_csg_rows = [{"type": "SYN casing", "od": 9.611, "id": 8.703, "from": 0.0, "to": 1000.0},
                           {"type": "Open Hole", "od": 8.5, "id": 8.5, "from": 1000.0, "to": 3000.0}]
        w13.hy_nzl_rows = [{"size": 12, "qty": 3}]
        w13._hy_update_tfa()
        w13.hy_bit_diameter.setValue(8.5)
        w13.hy_model.setCurrentText("Bingham Plastic")
        w13.hy_wt.setCurrentText("Vertical")
        w13.hy_bit_dep.setValue(3000.0)
        w13.hy_confirm_defaults.setChecked(True)
        w13._hy_run_calc()
        return w13.hy_result

    plain = run([{"type": "Drill Pipe", "od": 4.871, "id": 4.013, "length": 3000.0, "weight": 18.7}])
    linked = run([_library_pipe(db, 3000.0)])
    assert not plain.errors and linked.total_loss_psi == plain.total_loss_psi
    assert linked.ecd_at_bit_ppg == plain.ecd_at_bit_ppg
    case = w13.case_bar.save_case("SYN hydraulics from the library")
    assert case["method_version"] == "M126 circulating-system hydraulics v1"
    assert case["inputs"]["extra:pipes"]["value"][0][rb.BINDING_KEY]["contract"] == rb.CONTRACT_VERSION
    assert ch.recalculate_entry(_entry(db, case["id"]))["status"] == "MATCH"
    w13.hy_pipe_rows = []
    w13.case_bar.reopen(case["id"])
    assert w13.hy_pipe_rows[0][rb.BINDING_KEY]["snapshot"]["set_name"] == "SYN library"
    assert "Library references: 1 MATCH" in w13.case_bar.status.text()


# ------------------------------------------------------------------------------ M187 Weight / T&D

def test_weight_case_with_a_library_component_matches_the_weight_card_golden(w13, env):
    db = env[0]
    assert w13.calculator_finder.open_path("Weight")
    w13.wt_pipes[:] = [_library_pipe(db, 3000.0)]
    w13._wt_refresh_table()
    w13.wt_mw.setValue(75.0)
    w13.wt_inc.setValue(0.0)
    w13.wt_tds.setValue(40.0)
    w13.wt_friction.setValue(0.25)
    w13.wt_wob.setValue(0.0)
    w13._wt_calculate()
    case = w13.case_bar.save_case("SYN weight from the library")
    assert case["method_version"] == "M127 weight card and soft-string T&D v1"
    air = 18.7 * 3000.0 * 3.28084 / 1000.0                                   # klbf, closed form
    assert _value(case, "air_weight_klbf") == pytest.approx(air, rel=1e-6)
    assert _value(case, "buoyed_weight_klbf") == pytest.approx(air * (1 - (75.0 / 7.48) / 65.5), rel=1e-6)
    assert case["inputs"]["extra:pipes"]["value"][0][rb.BINDING_KEY]["fields"]["weight"] == "weight_ppf"
    assert ch.recalculate_entry(_entry(db, case["id"]))["status"] == "MATCH"
    w13.case_bar.reopen(case["id"])
    assert "Library references: 1 MATCH" in w13.case_bar.status.text()


# -------------------------------------------------------------------------------- M188 Casing strength

def test_casing_from_the_library_keeps_yield_unknown_and_records_the_snapshot(w13, env):
    db = env[0]
    assert w13.calculator_finder.open_path("CSG/CMT › Casing Strength")
    origin = w13.load_casing_from_library(snap(db, "SYN-CSG-96"))
    assert origin["kind"] == "reference" and w13.csg_yield.value() == 0.0
    assert w13.csg_provenance() == {"od_in": "reference", "id_in": "reference", "wall_in": "reference",
                                    "weight_ppf": "reference", "yield_psi": "unknown"}
    assert "yield strength" in w13.csg_source_label.text()
    w13._csg_calc_strength()
    assert w13.csg_burst_res.text().startswith("Not calculated: yield strength unknown")
    w13.csg_yield.setValue(80000.0)
    w13._csg_calc_strength()
    case = w13.case_bar.save_case("SYN casing from the library")
    assert case["method_version"] == "M127 casing pipe-body strength v1"
    prov = case["inputs"]["extra:provenance"]["value"]
    assert prov["fields"]["yield_psi"] == "user" and prov["fields"]["od_in"] == "reference"
    assert prov["origin"]["tubular_reference"]["snapshot"]["spec"]["designation"] == "SYN-CSG-96"
    assert _value(case, "burst_rating_psi") == pytest.approx(0.875 * 2 * 80000 * 0.454 / 9.611, abs=0.06)
    assert w13._csg_last_run["source"]["tubular_reference"] == prov["origin"]["tubular_reference"]
    assert ch.recalculate_entry(_entry(db, case["id"]))["status"] == "MATCH"
    w13._csg_reset_origin()
    w13.case_bar.reopen(case["id"])
    assert "tubular library SYN library v1, SYN-CSG-96" in w13.csg_source_label.text()
    assert w13.csg_provenance()["od_in"] == "reference" and "1 MATCH" in w13.case_bar.status.text()
    w13.csg_od.setValue(9.7)
    assert w13.csg_provenance()["od_in"] == "user"


def test_casing_wall_missing_from_the_library_is_derived_and_labelled(w13, env):
    assert w13.calculator_finder.open_path("CSG/CMT › Casing Strength")
    w13.load_casing_from_library(snap(env[0], "SYN-CSG-NOWALL"))
    assert w13.csg_wall.value() == pytest.approx((7.011 - 6.183) / 2.0, abs=5e-4)
    prov = w13.csg_provenance()
    assert prov["wall_in"] == "derived" and prov["weight_ppf"] == prov["yield_psi"] == "unknown"
    assert "Wall derived as (OD - ID) / 2" in w13.csg_source_label.text()
    bad = snap(env[0], "SYN-CSG-96")
    bad["item_fingerprint"] = "0" * 64
    assert w13.load_casing_from_library(bad) is None and "NOT USED" in w13.csg_source_label.text()


def test_a_failing_library_check_is_reported_unreadable_never_match(w13, env, monkeypatch):
    def broken(*_a, **_k):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(rb, "drift_report", broken)
    report = w13.case_bar.reference_report({"inputs": {}})
    assert [r["state"] for r in report] == [rb.UNREADABLE] and "RuntimeError" in report[0]["message"]


def test_casing_item_without_an_id_leaves_id_and_wall_unknown(w13, env):
    assert w13.calculator_finder.open_path("CSG/CMT › Casing Strength")
    w13.load_casing_from_library(snap(env[0], "SYN-CSG-NOID"))
    prov = w13.csg_provenance()
    assert prov["od_in"] == "reference" and prov["id_in"] == prov["wall_in"] == prov["weight_ppf"] == "unknown"
    w13.csg_yield.setValue(80000.0)
    w13._csg_calc_strength()
    assert w13.csg_burst_res.text().startswith("Not calculated")


# ------------------------------------------------------------------------------------ M184 Architecture

def test_architecture_revision_pins_the_snapshot_and_an_edit_drops_it(env):
    db, ids, _path = env
    assert all(rb.BINDING_KEY not in item for item in wa.normalize(ARCH)[0])       # old revisions: same SHA
    binding = rb.make_binding(snap(db, "SYN-CSG-96"), rb.ARCHITECTURE_FIELDS)
    items = json.loads(json.dumps(ARCH))
    items[1].update(od_in=9.611, id_in=8.703, weight_ppf=46.1, grade="SYN-80", tubular_reference=binding,
                    hole_in=12.25)
    rev = wa.save_revision(db, ids["A"][0], items, wellbore_id=ids["A"][1])
    stored = wa.get_revision(db, rev["id"])
    assert stored["components"][1][rb.BINDING_KEY] == binding
    inputs = wa.casing_inputs(stored["components"], "9-5/8 csg")
    assert inputs["tubular_reference"] == binding and inputs["provenance"]["yield_psi"] == "unknown"
    assert rb.drift_report(db, stored["components"])[0]["state"] == rb.MATCH
    edited = json.loads(json.dumps(items))
    edited[1]["od_in"] = 9.625
    assert rb.BINDING_KEY not in wa.normalize(edited)[0][1]
    assert "tubular_reference" not in wa.casing_inputs(ARCH, "9-5/8 csg")


def test_w3b_library_pick_is_frozen_reloaded_and_reaches_casing_strength(app, env, monkeypatch):
    from tabs import w13_Engineering_Calculator as w13_module
    from tabs.w3b_wellbore_schematic_tab import WellboreSchematicTab

    db, ids, _path = env
    tab = WellboreSchematicTab(db)
    calc = None
    try:
        tab.current_well_id = ids["A"][0]
        tab.architecture_panel.refresh()
        tab.schematic = wa.to_schematic(ARCH)
        tab._sync_tables_to_schematic()
        assert not tab.apply_library_to_casing(7, snap(db, "SYN-CSG-96"))
        assert tab.apply_library_to_casing(0, snap(db, "SYN-CSG-96"))
        casing = tab.schematic.casings[0]
        assert (casing.od_inch, casing.id_inch, casing.weight_ppf, casing.grade) == (9.611, 8.703, 46.1, "SYN-80")
        assert tab.casing_table.item(0, 1).text() == "9.611" and "SYN-CSG-96" in tab.casing_lib_label.text()
        rev = tab.architecture_panel.freeze_current()
        frozen = next(c for c in rev["components"] if c["kind"] == "casing" and c["name"] == casing.name)
        assert frozen[rb.BINDING_KEY]["snapshot"]["set_version"] == 1
        tab.schematic = wa.to_schematic([])
        tab.architecture_panel.table.selectRow(0)
        assert tab.architecture_panel.load_selected()
        assert tab.schematic.casings[0].tubular_reference == frozen[rb.BINDING_KEY]
        assert tab.apply_library_to_casing(1, snap(db, "SYN-CSG-NOID"))
        assert tab.schematic.casings[1].id_inch is None and "unavailable: id_in" in tab.casing_lib_label.text()
        monkeypatch.setattr(w13_module.QMessageBox, "information", lambda *a, **k: None)
        calc = w13_module.EngineeringCalculatorTab(db)
        calc.on_well_changed(ids["A"][0], {"name": "SYN-A"})
        origin = calc.load_casing_from_architecture("9-5/8 csg")
        assert origin["tubular_reference"]["snapshot"]["spec"]["designation"] == "SYN-CSG-96"
        assert calc.csg_provenance()["od_in"] == "architecture"
    finally:
        tab.deleteLater()
        if calc is not None:
            calc.deleteLater()
        app.processEvents()


# ------------------------------------------------------------------- M165 / M189 real persistence

def test_snapshots_survive_closing_and_reopening_the_database_file(env, tmp_path, monkeypatch):
    from core import calculation_cases as cc

    db, ids, path = env
    binding = rb.make_binding(snap(db, "SYN-DP-48"), rb.PIPE_COMPONENT_FIELDS)
    case = cc.save_case(db, calculator="Weight", name="SYN persisted", inputs={"extra:pipes": {"value": [
        {"type": "Drill Pipe", "od": 4.871, rb.BINDING_KEY: binding}]}}, results={"x": {"value": 1}},
        well_id=ids["A"][0])
    db.close()
    again = _open(path, tmp_path, monkeypatch)
    try:
        stored = cc.get_case(again, case["id"])["inputs"]["extra:pipes"]["value"][0][rb.BINDING_KEY]
        assert stored == binding and tr.verify_snapshot(stored["snapshot"]) == []
        assert [r["state"] for r in rb.drift_report(again, cc.get_case(again, case["id"])["inputs"])] == [rb.MATCH]
    finally:
        again.close()
    assert math.isclose(binding["snapshot"]["spec"]["nominal_od_in"], 4.871)


def test_a_published_set_is_immutable_at_the_storage_layer_and_drafts_stay_editable(env):
    import sqlite3

    db, _ids, path = env
    published = next(s for s in tr.list_sets(db) if s["status"] == tr.PUBLISHED)
    draft = tr.create_set(db, "SYN library")                               # v2 draft copies the items
    with sqlite3.connect(path) as connection:
        item = connection.execute("SELECT id FROM tubular_reference_items WHERE set_id = ?",
                                  (published["id"],)).fetchone()[0]
        draft_item = connection.execute("SELECT id FROM tubular_reference_items WHERE set_id = ?",
                                        (draft["id"],)).fetchone()[0]
        for sql, args, message in [
            ("UPDATE tubular_reference_sets SET notes = 'x' WHERE id = ?", (published["id"],), "immutable"),
            ("UPDATE tubular_reference_sets SET status = 'DRAFT' WHERE id = ?", (published["id"],), "immutable"),
            ("DELETE FROM tubular_reference_sets WHERE id = ?", (published["id"],), "never deleted"),
            ("UPDATE tubular_reference_items SET weight_ppf = 1 WHERE id = ?", (item,), "immutable"),
            ("UPDATE tubular_reference_items SET set_id = ? WHERE id = ?", (published["id"], draft_item), "immutable"),
            ("DELETE FROM tubular_reference_items WHERE id = ?", (item,), "never deleted"),
            ("INSERT INTO tubular_reference_items (set_id, component_type, origin, payload_json, fingerprint) "
             "VALUES (?, 'DP', 'user', '{}', 'f')", (published["id"],), "no new items"),
        ]:
            with pytest.raises(sqlite3.IntegrityError, match=message):
                connection.execute(sql, args)
        connection.execute("UPDATE tubular_reference_sets SET notes = 'draft note' WHERE id = ?", (draft["id"],))
        connection.execute("DELETE FROM tubular_reference_items WHERE id = ?", (draft_item,))
        connection.rollback()
    assert tr.publish_set(db, draft["id"])["version"] == 2                 # DRAFT -> PUBLISHED still works
    assert rb.drift(db, snap(db, "SYN-DP-48")).state == rb.MATCH
