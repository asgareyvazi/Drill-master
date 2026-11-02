"""M74: immutable, validated well architecture revisions, schematic and cement geometry.

SYNTHETIC databases (fresh and upgraded); offscreen Qt for the W3b page.
Cement references are hand arithmetic here: annular capacity
(Dh^2 - Dp^2) / 1029.4 bbl/ft, times 3.28084 ft/m.
"""
from __future__ import annotations

import copy
import sqlite3

import pytest
from sqlalchemy import text

from core import survey_revisions as sr
from core import well_architecture as wa
from core.authorization import AuthorizationError
from tests.test_database_migration_acceptance import _build_old_schema
from tests.test_m70_integrity import NEW_TABLES, _count, _open, _seed

FT_PER_M = 3.28084
ARCH_ROWS = "SELECT COUNT(*) FROM well_architecture_revisions"
ARCH = [
    {"kind": "section", "name": "12-1/4 in hole", "top_md": 0, "bottom_md": 1000, "hole_in": 12.25},
    {"kind": "casing", "name": "9-5/8 csg", "top_md": 0, "bottom_md": 1000, "od_in": 9.625, "id_in": 8.681,
     "hole_in": 12.25, "grade": "SYN-80", "weight_ppf": 47},
    {"kind": "shoe", "name": "9-5/8 csg", "top_md": 1000},
    {"kind": "cement", "name": "9-5/8 csg", "top_md": 500, "bottom_md": 1000},
    {"kind": "liner", "name": "7 liner", "top_md": 900, "bottom_md": 2000, "od_in": 7.0, "id_in": 6.184,
     "hole_in": 8.5},
    {"kind": "shoe", "name": "7 liner", "top_md": 2000},
    {"kind": "cement", "name": "7 liner", "top_md": 900, "bottom_md": 2000},
    {"kind": "tubing", "name": "Tubing", "top_md": 0, "bottom_md": 1900, "od_in": 3.5, "id_in": 2.992},
    {"kind": "packer", "name": "SYN packer", "top_md": 1850},
    {"kind": "formation", "name": "SYN F1", "top_md": 0, "bottom_md": 800},
    {"kind": "formation", "name": "SYN F2", "top_md": 800, "bottom_md": 2000},
    {"kind": "accessory", "name": "SYN float collar", "top_md": 1960},
]


def _with(index, **changes):
    items = copy.deepcopy(ARCH)
    items[index].update(changes)
    return items


@pytest.fixture(params=["fresh", "upgraded"])
def env(request, tmp_path, monkeypatch):
    path = tmp_path / f"{request.param}.sqlite"
    if request.param == "upgraded":
        _build_old_schema(path, 5)
        with sqlite3.connect(path) as connection:
            for table in NEW_TABLES + ("survey_revisions", "well_architecture_revisions"):
                connection.execute(f"DROP TABLE IF EXISTS {table}")
    manager = _open(path, tmp_path, monkeypatch)
    yield manager, path, _seed(manager)
    manager.close()


# ---- validation ------------------------------------------------------------------------------
def test_a_consistent_architecture_validates_cleanly():
    assert wa.validate(ARCH) == {"errors": [], "warnings": []}


@pytest.mark.parametrize("items, fragment", [
    (_with(4, od_in=9.0), "does not fit inside the host"),
    (_with(4, top_md=1500), "not inside a casing or liner"),
    (_with(2, top_md=990), "is not the string bottom"),
    (_with(3, bottom_md=1200), "outside the string"),
    (_with(1, od_in=12.5), "does not fit the 12.25 in hole"),
    (_with(1, id_in=9.625), "ID must be smaller than OD"),
    (_with(10, top_md=700), "overlaps"),
    (_with(8, top_md=1950), "outside every tubing string"),
    (_with(0, kind="riser"), "unknown kind"),
    (_with(9, bottom_md=0), "bottom MD must be below top MD"),
    (_with(9, top_md=-5), "must not be negative"),
    (_with(1, od_in="nan"), "must be finite"),
    (_with(1, od_in="9 5/8"), "is not a number"),
    (_with(7, name="7 liner"), "duplicate string name"),
    (_with(6, name="5 liner"), "names no casing/liner/tubing string"),
    (_with(8, top_md=None), "a depth (top MD) is required"),
    (_with(11, name=""), "a name is required"),
])
def test_each_rule_rejects_its_mutation(items, fragment):
    errors = wa.validate(items)["errors"]
    assert any(fragment in e for e in errors), errors


def test_unknown_sizes_stay_unknown_and_are_not_judged():
    items, _ = wa.normalize(_with(7, od_in="", id_in=None))
    assert items[7]["od_in"] is None and items[7]["id_in"] is None          # never 0
    result = wa.validate(_with(7, od_in="", id_in=None))
    assert result["errors"] == [] and any("OD unknown" in w for w in result["warnings"])
    assert any("not run from surface" in w for w in wa.validate(_with(1, top_md=10))["warnings"])


# ---- persistence ------------------------------------------------------------------------------
def test_revisions_are_numbered_tied_and_refused_when_invalid_or_foreign(env):
    manager, path, ids = env
    (well, bore), (other_well, other_bore) = ids["A"], ids["B"]
    survey = sr.save_revision(manager, well, [{"md": 0, "inc": 0, "azi": 0}, {"md": 500, "inc": 0, "azi": 0}],
                              depth_datum="RKB", azimuth_reference="true")
    first = wa.save_revision(manager, well, ARCH, wellbore_id=bore, survey_revision_id=survey["id"])
    assert (first["revision"], first["component_count"], first["schema_version"]) == (1, 12, wa.ARCHITECTURE_VERSION)
    assert first["components_sha256"] == wa.components_sha256(first["components"])
    second = wa.save_revision(manager, well, _with(9, name="SYN F1b"), parent_id=first["id"])
    assert second["revision"] == 2 and second["parent_id"] == first["id"]
    assert [r["revision"] for r in wa.list_revisions(manager, well)] == [2, 1]
    before = _count(path, ARCH_ROWS)
    for kwargs, fragment in [({"wellbore_id": other_bore}, "wellbore"),
                             ({"survey_revision_id": 999_999}, "survey revision"),
                             ({"parent_id": 999_999}, "parent")]:
        with pytest.raises(wa.ArchitectureError, match=fragment):
            wa.save_revision(manager, well, ARCH, **kwargs)
    with pytest.raises(wa.ArchitectureError, match="Not saved"):
        wa.save_revision(manager, well, _with(4, od_in=9.0))
    with pytest.raises(wa.ArchitectureError, match="no components"):
        wa.save_revision(manager, well, [])
    assert _count(path, ARCH_ROWS) == before
    assert wa.list_revisions(manager, other_well) == []
    assert wa.get_revision(manager, first["id"])["components"] == first["components"]


def test_a_saved_revision_cannot_be_changed_by_sql_or_orm_and_goes_with_its_well(env):
    from core.database import WellArchitectureRevision

    manager, path, ids = env
    well = ids["A"][0]
    rev = wa.save_revision(manager, well, ARCH)
    with pytest.raises(Exception, match="immutable"):
        with manager.session_scope() as session:
            session.execute(text("UPDATE well_architecture_revisions SET components_json='[]' WHERE id=:i"),
                            {"i": rev["id"]})
    with pytest.raises(Exception, match="immutable"):
        with manager.session_scope() as session:
            session.get(WellArchitectureRevision, rev["id"]).note = "edited"
    with pytest.raises(Exception, match="immutable"):
        with manager.session_scope() as session:
            session.query(WellArchitectureRevision).update({"revision": 7})
    assert wa.get_revision(manager, rev["id"])["note"] == ""
    manager.delete_well(well)
    assert _count(path, ARCH_ROWS) == 0


def test_viewers_cannot_save_an_architecture(tmp_path, monkeypatch):
    from tests.test_data_layer_authorization import Principal

    path = tmp_path / "authz.sqlite"
    manager = _open(path, tmp_path, monkeypatch)
    ids = _seed(manager)
    users = dict(sqlite3.connect(path).execute("SELECT username, id FROM users").fetchall())
    manager.enforce_authorization(Principal("viewer", users["admin"], "viewer"))
    with pytest.raises((AuthorizationError, PermissionError)):
        wa.save_revision(manager, ids["A"][0], ARCH)
    manager.close()


# ---- schematic and cement geometry ---------------------------------------------------------------
def test_the_schematic_is_generated_from_records_and_round_trips():
    schematic = wa.to_schematic(ARCH, well_name="SYN-A")
    assert [c.name for c in schematic.casings] == ["9-5/8 csg", "7 liner"]
    assert schematic.casings[0].show_cement and schematic.casings[0].cement_top_m == 500
    assert schematic.tubing_od_inch == 3.5 and schematic.total_depth_m == 2000
    back = wa.from_schematic(schematic)
    assert wa.validate(back)["errors"] == []
    kinds = sorted(i["kind"] for i in back)
    assert kinds.count("shoe") == 2 and kinds.count("cement") == 2 and "packer" in kinds


def test_cement_annulus_matches_hand_arithmetic_and_never_assumes_a_hole_size():
    result = wa.cement_annulus(ARCH, "7 liner")
    lap, open_hole = result["intervals"]
    assert (lap["top_md"], lap["bottom_md"], lap["outer"]) == (900, 1000, "9-5/8 csg")
    assert lap["volume_bbl"] == pytest.approx((8.681 ** 2 - 7.0 ** 2) / 1029.4 * FT_PER_M * 100, rel=1e-12)
    assert open_hole["outer"] == "open hole"
    assert open_hole["volume_bbl"] == pytest.approx((8.5 ** 2 - 7.0 ** 2) / 1029.4 * FT_PER_M * 1000, rel=1e-12)
    assert result["total_bbl"] == pytest.approx(lap["volume_bbl"] + open_hole["volume_bbl"])
    assert "WORKSHEET" in result["label"]
    unknown = wa.cement_annulus(_with(4, hole_in=None), "7 liner")
    assert unknown["intervals"][1]["volume_bbl"] is None and unknown["total_bbl"] is None
    assert wa.cement_annulus(_with(4, hole_in=None), "7 liner", open_hole_in=8.5)["total_bbl"] == \
        pytest.approx(result["total_bbl"])
    with pytest.raises(wa.ArchitectureError):
        wa.cement_annulus(ARCH, "Tubing")


# ---- the W3b page ---------------------------------------------------------------------------
def test_w3b_architecture_page_freezes_reloads_and_derives_cement(tmp_path, monkeypatch):
    from PySide6 import QtWidgets

    from tabs.w3b_wellbore_schematic_tab import WellboreSchematicTab

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    manager = _open(tmp_path / "w3b.sqlite", tmp_path, monkeypatch)
    ids = _seed(manager)
    tab = WellboreSchematicTab(manager)
    try:
        panel = tab.architecture_panel
        tab.current_well_id = ids["A"][0]
        panel.refresh()
        tab.schematic = wa.to_schematic(_with(4, od_in=9.0))
        assert panel.freeze_current() is None and panel.status.text().startswith("Not saved")
        tab.schematic = wa.to_schematic(ARCH)
        assert panel.validate_current()["errors"] == []
        rev = panel.freeze_current()
        assert rev["revision"] == 1 and panel.table.rowCount() == 1
        tab.schematic = wa.to_schematic([])
        panel.table.selectRow(0)
        assert panel.load_selected() and [c.name for c in tab.schematic.casings] == ["9-5/8 csg", "7 liner"]
        panel.string_combo.setCurrentText("7 liner")
        cement = panel.cement_selected()
        assert cement["architecture_revision_id"] == rev["id"] and "WORKSHEET" in panel.status.text()
        case = panel.save_cement_case()
        assert case["inputs"]["architecture_revision_id"]["value"] == rev["id"]
        assert case["inputs"]["components_sha256"]["value"] == rev["components_sha256"]
        assert case["results"]["total_bbl"]["value"] == pytest.approx(cement["total_bbl"])
        assert "WORKSHEET" in case["note"]
    finally:
        tab.deleteLater()
        app.processEvents()
        manager.close()
