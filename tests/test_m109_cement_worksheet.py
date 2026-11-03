"""M109: the cement worksheet as a contract with a re-run adapter (new linked case), labelled
"WORKSHEET — NOT A CEMENT DESIGN APPROVAL"; nothing (yield, sacks) is inferred from a grade or class.

Goldens are hand arithmetic (annular capacity (D² − d²) / 1029.4 bbl/ft, 3.28084 ft/m). Synthetic wells,
temporary SQLite, offscreen Qt.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets  # noqa: E402

from core import calculation_cases as cc  # noqa: E402
from core import calculation_history as ch  # noqa: E402
from core import well_architecture as wa  # noqa: E402
from tests.test_m70_integrity import _open, _seed  # noqa: E402
from tests.test_m74_well_architecture import ARCH  # noqa: E402
from tests.test_m88_history_lineage import _tamper  # noqa: E402

FT_PER_M = 3.28084
LABEL = "WORKSHEET — NOT A CEMENT DESIGN APPROVAL"


def _cap(outer, inner):
    return (outer ** 2 - inner ** 2) / 1029.4 * FT_PER_M      # bbl per metre


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def env(tmp_path, monkeypatch):
    path = tmp_path / "m109.sqlite"
    manager = _open(path, tmp_path, monkeypatch)
    ids = _seed(manager)
    yield manager, path, ids
    manager.close()


def _saved_case(manager, well, *, caliper=9.0, excess=20.0):
    rev = wa.save_revision(manager, well, ARCH)
    work = {**wa.cement_annulus(rev["components"], "7 liner", caliper_in=caliper, excess_pct=excess),
            "architecture_revision_id": rev["id"], "architecture_revision": rev["revision"],
            "components_sha256": rev["components_sha256"], "open_hole_in": None}
    inputs, results = wa.cement_case_payload(work)
    case = cc.save_case(manager, calculator=wa.CEMENT_CALCULATOR, name="SYN cement 7 liner", inputs=inputs,
                        results=results, method=wa.CEMENT_WORKSHEET_METHOD, method_version=wa.CEMENT_WORKSHEET_VERSION,
                        well_id=well, note=f"{LABEL} — {work['label']}")
    return rev, case


def _entry(manager, case_id, well):
    return next(e for e in ch.load_history(manager, well_id=well) if e.key == f"calculation_cases:{case_id}")


def test_the_contract_names_every_field_and_infers_nothing():
    contract = wa.CEMENT_CONTRACT
    assert contract["label"] == LABEL == wa.CEMENT_WORKSHEET_LABEL
    assert contract["method"] == wa.CEMENT_WORKSHEET_METHOD and contract["version"] == wa.CEMENT_WORKSHEET_VERSION
    assert [f["id"] for f in contract["inputs"]] == ["architecture_revision_id", "architecture_revision",
                                                     "components_sha256", "string", "open_hole_in", "caliper_in",
                                                     "excess_pct"]
    assert {f["unit"] for f in contract["inputs"] if f["id"] in ("open_hole_in", "caliper_in")} == {"in"}
    assert any("yield" in item and "never inferred" in item for item in contract["not_inferred"])
    result = wa.cement_annulus(ARCH, "7 liner")
    assert not any(k in result for k in ("yield", "sacks", "slurry_density", "thickening_time"))
    casing = wa.casing_inputs([dict(c, grade="P110") if c.get("name") == "7 liner" else c for c in ARCH], "7 liner")
    assert casing["values"]["grade"] == "P110" and casing["values"]["yield_psi"] is None   # never from the grade
    assert casing["provenance"]["yield_psi"] == "unknown"


def test_a_stored_worksheet_reruns_to_match_and_is_labelled(env):
    manager, _path, ids = env
    well = ids["A"][0]
    _rev, case = _saved_case(manager, well)
    entry = _entry(manager, case["id"], well)
    assert entry.scope == LABEL
    assert ch.entry_status(entry)["reproducible"] == "REPRODUCIBLE"
    outcome = ch.recalculate_entry(entry, db=manager)
    assert outcome["status"] == "MATCH" and LABEL in outcome["detail"], outcome
    golden = _cap(8.681, 7.0) * 100 + _cap(9.0, 7.0) * 1000 * 1.2                  # lap + open hole with 20 %
    assert outcome["values"]["total_bbl"] == pytest.approx(golden, rel=1e-12)
    assert ch.recalculate_entry(entry)["status"] == "NOT_REPRODUCIBLE"              # without the database


def test_a_rerun_is_stored_as_a_new_linked_case_and_the_original_is_unchanged(app, env):
    from tabs.calculation_history_tab import CalculationHistoryTab

    manager, _path, ids = env
    well = ids["A"][0]
    _rev, case = _saved_case(manager, well)
    tab = CalculationHistoryTab(manager)
    try:
        tab.set_well(well)
        tab.select_rows([i for i, e in enumerate(tab.entries) if e.key == f"calculation_cases:{case['id']}"])
        assert tab.recalculate()["status"] == "MATCH"
        new = tab.save_recalculation()
    finally:
        tab.deleteLater()
        app.processEvents()
    assert new["id"] != case["id"] and new["method"] == wa.CEMENT_WORKSHEET_METHOD
    assert new["method_version"] == wa.CEMENT_WORKSHEET_VERSION and new["calculator"] == wa.CEMENT_CALCULATOR
    assert new["note"].startswith(LABEL) and f"re-run of case #{case['id']}: MATCH" in new["note"]
    assert new["inputs"] == case["inputs"] and new["results"] == case["results"]
    rerun = _entry(manager, new["id"], well)
    assert ch.entry_status(rerun)["reproducible"] == "REPRODUCIBLE"                  # a full worksheet case again
    links = {(i["direction"], i["key"], i.get("link_type"), i.get("verification_status"))
             for i in ch.lineage(manager, rerun)}
    assert ("source", f"calculation_cases:{case['id']}", "rerun_of", "MATCH") in links
    assert _entry(manager, case["id"], well).results == case["results"]             # original untouched


def test_a_changed_stored_result_or_label_is_different(env):
    manager, _path, ids = env
    well = ids["A"][0]
    _rev, case = _saved_case(manager, well)
    results = {k: dict(v) for k, v in case["results"].items()}
    results["interval_2"]["value"] += 0.01
    outcome = wa.verify_cement_case(manager, case["inputs"], results, wa.CEMENT_WORKSHEET_VERSION)
    assert outcome["status"] == "DIFFERENT" and [d["field_id"] for d in outcome["differences"]] == ["interval_2"]
    relabelled = {k: dict(v) for k, v in case["results"].items()}
    relabelled["interval_1"]["label"] = "0-100 m in open hole (recorded hole size)"
    outcome = wa.verify_cement_case(manager, case["inputs"], relabelled, wa.CEMENT_WORKSHEET_VERSION)
    assert outcome["status"] == "DIFFERENT" and outcome["differences"][0]["field_id"] == "interval_1"
    fewer = {k: v for k, v in case["results"].items() if k != "interval_2_excess"}
    outcome = wa.verify_cement_case(manager, case["inputs"], fewer, wa.CEMENT_WORKSHEET_VERSION)
    assert outcome["differences"] == [{"field_id": "interval_2_excess", "stored": None,
                                       "current": pytest.approx(0.2 * _cap(9.0, 7.0) * 1000, rel=1e-12)}]


def test_integrity_failures_are_unreadable_and_cannot_be_stored(env):
    manager, path, ids = env
    well = ids["A"][0]
    rev, case = _saved_case(manager, well)
    other = dict(case["inputs"], components_sha256=dict(case["inputs"]["components_sha256"], value="0" * 64))
    outcome = wa.verify_cement_case(manager, other, case["results"], wa.CEMENT_WORKSHEET_VERSION)
    assert outcome["status"] == "UNREADABLE" and "SHA-256 differs" in outcome["detail"]
    with pytest.raises(ValueError, match="Nothing to store"):
        wa.save_cement_rerun(manager, case["id"], other, outcome, well_id=well, wellbore_id=None, name="SYN")
    missing = dict(case["inputs"], architecture_revision_id={"label": "Architecture revision id", "value": 999999})
    assert wa.verify_cement_case(manager, missing, case["results"],
                                 wa.CEMENT_WORKSHEET_VERSION)["status"] == "UNREADABLE"
    _tamper(manager, path, "trg_well_architecture", "UPDATE well_architecture_revisions SET components_json = ? "
            "WHERE id = ?", ('[{"kind": "casing", "name": "x"}]', rev["id"]))
    outcome = ch.recalculate_entry(_entry(manager, case["id"], well), db=manager)
    assert outcome["status"] == "UNREADABLE" and "SHA-256" in outcome["detail"]


def test_reproducibility_reasons_are_exact():
    inputs = {"architecture_revision_id": {"value": 1}, "components_sha256": {"value": "a" * 64},
              "string": {"value": ""}}
    assert wa.cement_reproducibility(inputs, wa.CEMENT_WORKSHEET_VERSION) == (
        "NOT REPRODUCIBLE", "the case does not record string")
    assert "not available" in wa.cement_reproducibility(inputs, "M88 something older")[1]
    full = dict(inputs, string={"value": "7 liner"})
    assert wa.cement_reproducibility(full, wa.CEMENT_WORKSHEET_VERSION)[0] == "REPRODUCIBLE"


def test_the_w13_cement_volume_contract_and_history_carry_the_label(env):
    from core import calculator_contracts as contracts

    assert contracts.CONTRACTS["CSG/CMT › Cement Volume"].limits.startswith(LABEL)
    manager, _path, ids = env
    well = ids["A"][0]
    case = cc.save_case(manager, calculator="CSG/CMT › Cement Volume", name="SYN W13 cement",
                        inputs={"x": {"label": "Hole", "value": 8.5, "unit": "in"}}, results={},
                        method="w13.cement.job_volumes", method_version="M87 cement job volume worksheet v1",
                        well_id=well)
    assert _entry(manager, case["id"], well).scope == LABEL


def test_the_architecture_panel_saves_through_the_shared_builder_with_the_label(app, env):
    from tabs.w3b_wellbore_schematic_tab import WellboreSchematicTab

    manager, _path, ids = env
    well = ids["A"][0]
    tab = WellboreSchematicTab(manager)
    try:
        tab.current_well_id = well
        panel = tab.architecture_panel
        panel.refresh()
        tab.schematic = wa.to_schematic(ARCH)
        panel.freeze_current()
        panel.table.selectRow(0)
        panel.string_combo.setCurrentText("7 liner")
        work = panel.cement_selected()
        assert panel.status.text().startswith(LABEL)
        case = panel.save_cement_case()
        assert LABEL in panel.status.text() and case["note"].startswith(LABEL)
        assert (case["inputs"], case["results"]) == wa.cement_case_payload(work)
        entry = _entry(manager, case["id"], well)
        assert ch.recalculate_entry(entry, db=manager)["status"] == "MATCH"
    finally:
        tab.deleteLater()
        app.processEvents()
