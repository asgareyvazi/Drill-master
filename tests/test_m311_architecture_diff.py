"""M311 (M274): component-level comparison of two frozen architecture revisions (SYNTHETIC)."""
from __future__ import annotations

import pytest

from core import architecture_diff as ad
from core import calculation_cases as cc
from core import well_architecture as wa
from synthetic_operations import build_synthetic_operations, make_file_database
from test_m74_well_architecture import ARCH


def _with(changes):
    out = []
    for comp in ARCH:
        key = (comp["kind"], comp["name"])
        if key in changes:
            if changes[key] is None:
                continue
            out.append({**comp, **changes[key]})
        else:
            out.append(dict(comp))
    return out


@pytest.fixture
def world(tmp_path):
    db = make_file_database(tmp_path / "m311.db")
    ids = build_synthetic_operations(db)
    yield db, ids
    db.engine.dispose()


def test_identical_components_are_identical():
    result = ad.compare_components(ARCH, [dict(c) for c in ARCH])
    assert result["identical"] and result["counts"][ad.UNCHANGED] == len(ARCH)
    assert ad.summary_lines(result)[0] == "identical components."


def test_changed_added_and_removed_components_are_named_with_old_and_new_values():
    newer = _with({("cement", "9-5/8 csg"): {"top_md": 300}, ("casing", "9-5/8 csg"): {"id_in": None},
                   ("accessory", "SYN float collar"): None})
    newer.append({"kind": "formation", "name": "SYN F3", "top_md": 2000, "bottom_md": 2100})
    result = ad.compare_components(ARCH, newer)
    rows = {(r["kind"], r["name"]): r for r in result["rows"]}
    cement = rows[("cement", "9-5/8 csg")]
    assert cement["status"] == ad.CHANGED and cement["changes"] == [{"field": "top_md", "old": 500.0, "new": 300.0}]
    casing = rows[("casing", "9-5/8 csg")]
    assert casing["changes"] == [{"field": "id_in", "old": 8.681, "new": None}]       # value -> unknown is a change
    assert rows[("accessory", "SYN float collar")]["status"] == ad.REMOVED
    assert rows[("formation", "SYN F3")]["status"] == ad.ADDED
    assert result["counts"] == {ad.ADDED: 1, ad.REMOVED: 1, ad.CHANGED: 2, ad.UNCHANGED: len(ARCH) - 3}
    assert result["affected_strings"] == ["9-5/8 csg"]
    text = " ".join(ad.summary_lines(result))
    assert "id_in 8.681 → unknown" in text and "top_md 500 → 300" in text
    assert "worksheets pinned to the older revision are not updated" in text


def test_duplicate_identities_are_matched_in_order_and_stated():
    older = ARCH + [{"kind": "formation", "name": "SYN F1", "top_md": 2000, "bottom_md": 2050}]
    newer = ARCH + [{"kind": "formation", "name": "SYN F1", "top_md": 2000, "bottom_md": 2060}]
    result = ad.compare_components(older, newer)
    second = [r for r in result["rows"] if r["name"] == "SYN F1"][1]
    assert second["changes"] == [{"field": "bottom_md", "old": 2050.0, "new": 2060.0}]
    assert any("occurs 2×" in n for n in result["notes"])


def test_revisions_are_ordered_checked_and_pinned_cases_listed(world):
    db, ids = world
    first = wa.save_revision(db, ids["dev"], ARCH)
    inputs, results = wa.cement_case_payload({**wa.cement_annulus(first["components"], "9-5/8 csg"),
                                              "architecture_revision_id": first["id"],
                                              "architecture_revision": first["revision"],
                                              "components_sha256": first["components_sha256"], "open_hole_in": None})
    case = cc.save_case(db, calculator=wa.CEMENT_CALCULATOR, name="SYN pinned", inputs=inputs, results=results,
                        well_id=ids["dev"])
    second = wa.save_revision(db, ids["dev"], _with({("cement", "9-5/8 csg"): {"top_md": 300}}),
                              parent_id=first["id"])
    result = ad.compare_revisions(db, second["id"], first["id"])                     # order does not matter
    assert (result["older"]["revision"], result["newer"]["revision"]) == (1, 2)
    assert [p["id"] for p in result["pinned_cases"]] == [case["id"]]
    assert "not recalculated" in ad.summary_lines(result)[-1]
    with pytest.raises(ad.ArchitectureDiffError):
        ad.compare_revisions(db, first["id"], first["id"])
    other = wa.save_revision(db, ids["qa"], ARCH)
    with pytest.raises(ad.ArchitectureDiffError):
        ad.compare_revisions(db, first["id"], other["id"])


def test_a_tampered_revision_is_never_compared(world):
    db, ids = world
    first = wa.save_revision(db, ids["dev"], ARCH)
    second = wa.save_revision(db, ids["dev"], ARCH)
    with db.engine.begin() as conn:
        for (name,) in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger' AND "
                                            "tbl_name='well_architecture_revisions'").fetchall():
            conn.exec_driver_sql(f"DROP TRIGGER {name}")
        conn.exec_driver_sql("UPDATE well_architecture_revisions SET components_json = "
                             "replace(components_json, '8.681', '8.5') WHERE id = ?", (second["id"],))
    with pytest.raises(wa.ArchitectureError, match="SHA-256"):
        ad.compare_revisions(db, first["id"], second["id"])


def test_architecture_panel_compares_with_the_previous_revision(world):
    from PySide6 import QtWidgets

    from tabs.w3b_wellbore_schematic_tab import WellboreSchematicTab

    db, ids = world
    wa.save_revision(db, ids["dev"], ARCH)
    wa.save_revision(db, ids["dev"], _with({("casing", "9-5/8 csg"): {"bottom_md": 1010},
                                            ("shoe", "9-5/8 csg"): {"top_md": 1010},
                                            ("cement", "9-5/8 csg"): {"bottom_md": 1010}}))
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tab = WellboreSchematicTab(db)
    try:
        tab.current_well_id = ids["dev"]
        panel = tab.architecture_panel
        panel.refresh()
        panel.table.selectRow(1)                                     # revisions are listed newest first
        assert not panel.compare_btn.isEnabled()                     # rev 1 has no older revision
        panel.table.selectRow(0)
        assert panel.compare_btn.isEnabled()
        panel.compare_btn.click()
        text = panel.status.text()
        assert text.startswith("Architecture rev 1 → rev 2") and "bottom_md 1000 → 1010" in text
        assert panel.last_comparison["affected_strings"] == ["9-5/8 csg"]
    finally:
        tab.deleteLater()
        app.processEvents()
