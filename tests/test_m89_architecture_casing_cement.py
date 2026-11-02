"""M89: casing inputs pinned to an architecture revision with per-value provenance; cement
worksheet with declared caliper and explicit open-hole excess; History lineage both ways.

Goldens are hand arithmetic (annular capacity (D^2 - d^2) / 1029.4 bbl/ft), offscreen Qt.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

from core import calculation_history as ch  # noqa: E402
from core import well_architecture as wa  # noqa: E402
from tests.test_m70_integrity import _open, _seed  # noqa: E402
from tests.test_m74_well_architecture import ARCH  # noqa: E402

FT_PER_M = 3.28084


def _cap(outer, inner):
    return (outer ** 2 - inner ** 2) / 1029.4 * FT_PER_M      # bbl per metre


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def env(tmp_path, monkeypatch):
    manager = _open(tmp_path / "m89.sqlite", tmp_path, monkeypatch)
    ids = _seed(manager)
    yield manager, ids
    manager.close()


# ---- cement worksheet --------------------------------------------------------------------------
def test_cement_caliper_and_excess_follow_hand_arithmetic():
    result = wa.cement_annulus(ARCH, "7 liner", caliper_in=9.0, excess_pct=20.0)
    lap, open_hole = result["intervals"]
    assert lap["outer_source"] == "9-5/8 csg ID" and lap["excess_bbl"] is None          # cased: no excess
    assert lap["volume_bbl"] == pytest.approx(_cap(8.681, 7.0) * 100, rel=1e-12)
    assert open_hole["outer_source"] == "declared average caliper" and open_hole["outer_id_in"] == 9.0
    base = _cap(9.0, 7.0) * 1000
    assert open_hole["base_volume_bbl"] == pytest.approx(base, rel=1e-12)
    assert open_hole["excess_bbl"] == pytest.approx(0.2 * base, rel=1e-12)
    assert open_hole["volume_bbl"] == pytest.approx(1.2 * base, rel=1e-12)
    assert result["total_bbl"] == pytest.approx(lap["volume_bbl"] + 1.2 * base, rel=1e-12)
    assert result["base_total_bbl"] == pytest.approx(lap["volume_bbl"] + base, rel=1e-12)
    assert result["label"] == "WORKSHEET (declared average caliper; excess 20 % on open hole (declared))"
    assert result["method"] == wa.CEMENT_WORKSHEET_METHOD and result["version"] == wa.CEMENT_WORKSHEET_VERSION


def test_no_excess_is_not_a_zero_excess_and_nominal_sizes_are_labelled():
    plain = wa.cement_annulus(ARCH, "7 liner")
    assert plain["intervals"][1]["outer_source"] == "recorded hole size"
    assert plain["intervals"][1]["excess_bbl"] is None and plain["label"] == "WORKSHEET (nominal sizes; no excess)"
    zero = wa.cement_annulus(ARCH, "7 liner", excess_pct=0.0)
    assert zero["intervals"][1]["excess_bbl"] == 0.0 and "excess 0 %" in zero["label"]
    assert zero["total_bbl"] == pytest.approx(plain["total_bbl"], rel=1e-12)
    override = wa.cement_annulus(ARCH, "7 liner", open_hole_in=8.75)
    assert override["intervals"][1]["outer_source"] == "open-hole size entered"


@pytest.mark.parametrize("kwargs, message", [
    ({"caliper_in": 6.5}, "not larger than the string OD"),
    ({"caliper_in": float("nan")}, "caliper"),
    ({"excess_pct": -5.0}, "excess"),
    ({"excess_pct": 600.0}, "excess"),
    ({"excess_pct": True}, "excess"),
])
def test_invalid_caliper_or_excess_is_refused(kwargs, message):
    with pytest.raises(wa.ArchitectureError, match=message):
        wa.cement_annulus(ARCH, "7 liner", **kwargs)


# ---- casing inputs -----------------------------------------------------------------------------
def test_casing_inputs_record_the_origin_of_every_value_and_never_infer_yield():
    data = wa.casing_inputs(ARCH, "9-5/8 csg")
    assert data["values"]["od_in"] == 9.625 and data["values"]["id_in"] == 8.681
    assert data["values"]["wall_in"] == pytest.approx((9.625 - 8.681) / 2, rel=1e-12)
    assert data["values"]["grade"] == "SYN-80" and data["values"]["yield_psi"] is None
    assert data["provenance"] == {"od_in": "architecture", "id_in": "architecture", "weight_ppf": "architecture",
                                  "grade": "architecture", "wall_in": "derived", "yield_psi": "unknown"}
    liner = wa.casing_inputs(ARCH, "7 liner")             # no weight, no grade recorded
    assert liner["provenance"]["weight_ppf"] == "unknown" and liner["provenance"]["grade"] == "unknown"
    assert liner["values"]["weight_ppf"] is None
    with pytest.raises(wa.ArchitectureError):
        wa.casing_inputs(ARCH, "SYN packer")


# ---- W13 casing page, end to end -------------------------------------------------------------
def test_w13_casing_from_architecture_reaches_history_with_lineage(app, env, monkeypatch):
    from tabs import w13_Engineering_Calculator as w13_module

    manager, ids = env
    well, other = ids["A"][0], ids["B"][0]
    arch = wa.save_revision(manager, well, ARCH, wellbore_id=ids["A"][1])
    monkeypatch.setattr(w13_module.QMessageBox, "information", lambda *a, **k: None)
    warnings = []
    monkeypatch.setattr(w13_module.QMessageBox, "warning", lambda *a, **k: warnings.append(a[2]))
    tab = w13_module.EngineeringCalculatorTab(manager)
    try:
        tab.on_well_changed(well, {"name": "SYN-A"})
        origin = tab.load_casing_from_architecture("9-5/8 csg")
        assert origin["architecture_revision_id"] == arch["id"] and origin["string"] == "9-5/8 csg"
        assert [tab.csg_arch_string.itemText(i) for i in range(tab.csg_arch_string.count())] == \
            ["9-5/8 csg", "7 liner", "Tubing"]
        assert tab.csg_od.value() == 9.625 and tab.csg_yield.value() == 0.0
        assert "Unknown: yield strength" in tab.csg_source_label.text()
        tab._csg_calc_strength()                           # yield unknown -> refused, nothing cached
        assert tab.csg_burst_res.text().startswith("Not calculated: yield strength unknown")
        assert tab._csg_last_run is None
        tab.csg_yield.setValue(80000)
        tab.csg_id_calc.setValue(8.6)                      # a user edit after loading
        tab._csg_calc_strength()
        source = tab._csg_last_run["source"]
        assert source["kind"] == "architecture" and source["components_sha256"] == arch["components_sha256"]
        assert source["provenance"] == {"od_in": "architecture", "id_in": "user", "wall_in": "derived",
                                        "weight_ppf": "architecture", "yield_psi": "user"}
        tab._csg_save_calculation()
        casing = next(e for e in ch.load_history(manager, well_id=well, sources=["Casing design"]))
        assert casing.name == f"Casing Strength - 9-5/8 csg (arch rev {arch['revision']})"
        assert casing.inputs["source"]["provenance"]["yield_psi"] == "user"
        assert ch.recalculate_entry(casing)["status"] == "MATCH"      # provenance does not affect reconstruction
        assert ("uses", f"well_architecture_revisions:{arch['id']}") in \
            {(i["direction"], i["key"]) for i in ch.lineage(manager, casing)}
        arch_entry = next(e for e in ch.load_history(manager, well_id=well, sources=["Well architecture"]))
        assert ("used_by", casing.key) in {(i["direction"], i["key"]) for i in ch.lineage(manager, arch_entry)}
        # another well: the origin no longer applies and an old run cannot be saved there
        tab._csg_calc_strength()
        tab.current_well_id = other                        # bypass the hook: the save guard must refuse
        tab._csg_save_calculation()
        assert warnings and "another well" in warnings[-1]
        assert ch.count_history(manager, well_id=other) == 0
        tab.on_well_changed(other, {"name": "SYN-B"})
        assert tab._csg_origin is None and tab.csg_arch_string.count() == 0
        assert tab.csg_provenance()["od_in"] == "user"
        assert tab.load_casing_from_architecture() is None and "no architecture revision" in \
            tab.csg_source_label.text()
    finally:
        tab.deleteLater()
        app.processEvents()


def test_w3b_cement_worksheet_with_caliper_and_excess_is_saved_with_lineage(app, env):
    from tabs.w3b_wellbore_schematic_tab import WellboreSchematicTab

    manager, ids = env
    well = ids["A"][0]
    tab = WellboreSchematicTab(manager)
    try:
        tab.current_well_id = well
        panel = tab.architecture_panel
        panel.refresh()
        tab.schematic = wa.to_schematic(ARCH)
        rev = panel.freeze_current()
        panel.table.selectRow(0)
        panel.string_combo.setCurrentText("7 liner")
        assert panel.excess_spin.text().strip() == "none" and panel.caliper_spin.text().strip() == "none"
        panel.caliper_spin.setValue(9.0)
        panel.excess_spin.setValue(20.0)
        work = panel.cement_selected()
        assert work["excess_pct"] == 20.0 and work["caliper_in"] == 9.0
        assert "declared average caliper" in panel.status.text() and "excess" in panel.status.text()
        case = panel.save_cement_case()
        entry = next(e for e in ch.load_history(manager, well_id=well) if e.key == f"calculation_cases:{case['id']}")
        assert entry.method == wa.CEMENT_WORKSHEET_METHOD and entry.version == wa.CEMENT_WORKSHEET_VERSION
        assert entry.inputs["excess_pct"]["value"] == 20.0 and entry.inputs["caliper_in"]["value"] == 9.0
        assert entry.results["base_total_bbl"]["value"] < entry.results["total_bbl"]["value"]
        assert ("uses", f"well_architecture_revisions:{rev['id']}") in \
            {(i["direction"], i["key"]) for i in ch.lineage(manager, entry)}
        assert ch.entry_status(entry)["reproducible"] == "NOT REPRODUCIBLE"     # worksheet: captured only
    finally:
        tab.deleteLater()
        app.processEvents()
