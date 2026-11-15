"""M205 / M206 / M207 / M221: missing casing weight stays None end to end, built-in presets are labelled
``LEGACY_PRESET — SOURCE UNVERIFIED`` (never manufacturer data), and the W3b schematic is a versioned,
ownership-checked JSON document that keeps library bindings, preset origins and missing values.

Real Qt widgets and a real SQLite file (``_open`` / ``_seed``). Every library item is SYNTHETIC (``SYN-*``).
"""
from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6 import QtWidgets  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402

from core import schematic_document as sd  # noqa: E402
from core import well_architecture as wa  # noqa: E402
from core.engineering import reference_binding as rb  # noqa: E402
from core.engineering import tubular_reference as tr  # noqa: E402
from core.engineering import value_provenance as vp  # noqa: E402
from tests.test_m70_integrity import _open, _seed  # noqa: E402
from tests.test_m74_well_architecture import ARCH  # noqa: E402

# A synthetic "manufacturer" entry (fictitious maker, fixture licence) - only to test the origin mapping.
MAKER = tr.Provenance(origin="manufacturer", manufacturer="SYN Maker (fictitious)", document="SYN maker sheet",
                      licence="synthetic test fixture")
USER = tr.Provenance(origin="user", entered_by="synthetic-tester", document="SYN sheet")
ITEMS = [tr.TubularSpec("CASING", "SYN-CSG-96", USER, grade="SYN-80", nominal_od_in=9.611, id_in=8.703,
                        weight_ppf=46.1),
         tr.TubularSpec("CASING", "SYN-CSG-NOWT", USER, nominal_od_in=7.013, id_in=6.211),
         tr.TubularSpec("CASING", "SYN-CSG-MAKER", MAKER, nominal_od_in=5.511, id_in=4.913, weight_ppf=17.3)]


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def env(tmp_path, monkeypatch):
    manager = _open(tmp_path / "m205.sqlite", tmp_path, monkeypatch)
    ids = _seed(manager)
    set_id = tr.create_set(manager, "SYN library")["id"]
    for spec in ITEMS:
        tr.add_item(manager, set_id, spec)
    tr.publish_set(manager, set_id)
    yield manager, ids
    manager.close()


@pytest.fixture
def w3b(app, env):
    from tabs.w3b_wellbore_schematic_tab import WellboreSchematicTab
    db, ids = env
    tab = WellboreSchematicTab(db)
    tab.current_well_id = ids["A"][0]
    yield tab, db, ids
    tab.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def snap(db, designation):
    return tr.reference_snapshot(next(r for r in tr.search(db) if r["spec"].designation == designation))


# ---------------------------------------------------------------- M205 weight
def test_missing_weight_stays_none_through_architecture_round_trip():
    components = [dict(c) for c in ARCH]
    for c in components:
        if c["kind"] == "casing":
            c.pop("weight_ppf", None)
    schematic = wa.to_schematic(components)
    assert schematic.casings and all(c.weight_ppf is None for c in schematic.casings)
    back = [c for c in wa.from_schematic(schematic) if c["kind"] in ("casing", "liner")]
    assert back and all(c["weight_ppf"] is None for c in back)


def test_explicit_weights_survive_and_zero_is_not_turned_into_none():
    from core.wellbore_schematic_engine import CasingData, ElementType, WellboreSchematic
    schematic = WellboreSchematic()
    schematic.casings = [CasingData("A", ElementType.CASING, 9.611, 8.703, 0, 900, weight_ppf=46.1),
                         CasingData("B", ElementType.CASING, 7.013, None, 0, 1500, weight_ppf=0.0)]
    weights = {c["name"]: c["weight_ppf"] for c in wa.from_schematic(schematic) if c["kind"] == "casing"}
    assert weights == {"A": 46.1, "B": 0.0}
    assert [c.weight_ppf for c in wa.to_schematic(wa.from_schematic(schematic)).casings] == [46.1, 0.0]


def test_library_item_without_weight_leaves_weight_unrecorded_and_the_table_shows_a_dash(w3b):
    tab, db, _ids = w3b
    tab.schematic = wa.to_schematic(ARCH)
    tab._sync_tables_to_schematic()
    assert tab.apply_library_to_casing(0, snap(db, "SYN-CSG-NOWT"))
    casing = tab.schematic.casings[0]
    assert casing.weight_ppf is None and casing.tubular_reference is not None
    assert tab.casing_table.item(0, 5).text() == "—"
    assert tab.casing_table.item(0, 6).text() == "Library SYN library v1"
    tab.refresh_drawing()                                   # rendering copes with None (no placeholder stored)
    assert casing.weight_ppf is None
    stored = json.loads(sd.dumps(tab.schematic, well_id=tab.current_well_id))
    assert stored["casings"][0]["weight_ppf"] is None and "casing" in stored["missing"][0]


def test_weight_column_edits_keep_none_distinct_from_numbers(w3b):
    tab, _db, _ids = w3b
    tab.schematic = wa.to_schematic(ARCH)
    tab._sync_tables_to_schematic()
    tab.casing_table.item(0, 5).setText("47.5")
    assert tab.schematic.casings[0].weight_ppf == 47.5
    tab.casing_table.item(0, 5).setText("—")
    assert tab.schematic.casings[0].weight_ppf is None


def test_auto_builder_reads_reported_weight_and_never_invents_one(env):
    from core.wellbore_schematic_engine import SchematicAutoBuilder, WellboreSchematic
    builder = SchematicAutoBuilder.__new__(SchematicAutoBuilder)
    rows = [{"type": "Surface", "od": 13.375, "id": 12.415, "from": 0, "to": 500, "weight": 68},
            {"type": "Production", "od": 7, "from": 0, "to": 2000},
            {"type": "Liner", "od": 5, "from": 1800, "to": 2500, "weight": 0}]
    builder.db = type("DB", (), {"get_casing_report": lambda self, **k: {"casing_json": json.dumps(rows)}})()
    schematic = WellboreSchematic()
    builder._add_casings_from_db(schematic, 1)
    assert [c.weight_ppf for c in schematic.casings] == [68.0, None, None]
    assert {c.value_source for c in schematic.casings} == {"casing report"}


# ---------------------------------------------------------------- M206 / M221 presets
def test_inventory_is_labelled_and_points_at_real_code():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert len(vp.INVENTORY) == len(vp.TABLES) >= 6
    for table in vp.INVENTORY:
        assert table.label in (vp.PRESET_LABEL, vp.UNKNOWN_DEFAULT_LABEL)
        path = table.location.split()[0]
        assert os.path.isfile(os.path.join(root, path)), path
    assert vp.PRESET_LABEL == "LEGACY_PRESET — SOURCE UNVERIFIED"
    assert vp.UNKNOWN_DEFAULT_LABEL == "LEGACY — SOURCE UNKNOWN"


def test_a_preset_is_never_reported_as_manufacturer_data():
    record = vp.preset_record("casing_db", '9-5/8" X', {"od": 9.625, "id": 8.835, "weight": 40})
    origins = vp.field_origins({"od": 9.625, "id": 8.835, "weight": 40, "grade": None}, preset=record)
    assert origins == {"od": vp.LEGACY_PRESET, "id": vp.LEGACY_PRESET, "weight": vp.LEGACY_PRESET,
                       "grade": vp.UNKNOWN}
    assert vp.MANUFACTURER not in origins.values()
    edited = vp.field_origins({"od": 9.7, "id": 8.835, "weight": 40}, preset=record)
    assert edited["od"] == vp.USER and not vp.preset_holds(record, {"od": 9.7, "id": 8.835, "weight": 40})
    assert record["registry"] == vp.REGISTRY_VERSION and record["origin"] == vp.LEGACY_PRESET
    with pytest.raises(KeyError):
        vp.preset_record("api_tables", "x", {})


def test_library_origin_is_the_items_declared_origin_only_while_unchanged(env):
    db, _ids = env
    binding = rb.make_binding(snap(db, "SYN-CSG-96"), rb.ARCHITECTURE_FIELDS)
    values = {"od_in": 9.611, "id_in": 8.703, "weight_ppf": 46.1, "grade": "SYN-80"}
    assert set(vp.field_origins(values, binding=binding).values()) == {vp.USER}       # the item says "user"
    assert vp.field_origins(dict(values, od_in=9.7), binding=binding)["od_in"] == vp.USER
    assert vp.field_origins({"wall_in": 0.454}, derived=["wall_in"]) == {"wall_in": vp.DERIVED}
    maker = rb.make_binding(snap(db, "SYN-CSG-MAKER"), rb.ARCHITECTURE_FIELDS)
    maker_values = {"od_in": 5.511, "id_in": 4.913, "weight_ppf": 17.3, "grade": None}
    assert vp.field_origins(maker_values, binding=maker) == {"od_in": vp.MANUFACTURER, "id_in": vp.MANUFACTURER,
                                                             "weight_ppf": vp.MANUFACTURER, "grade": vp.UNKNOWN}


def test_add_pipe_and_casing_dialogs_show_and_store_the_preset_label(app):
    from dialogs.engineering_dialogs import AddCasingDialog, AddPipeDialog
    pipe = AddPipeDialog(None)
    casing = AddCasingDialog(None)
    try:
        pipe.type_combo.setCurrentText("Drill Pipe")
        texts = [pipe.quick_combo.itemText(i) for i in range(1, pipe.quick_combo.count())]
        assert texts and all(t.endswith(f"[{vp.PRESET_LABEL}]") for t in texts)
        pipe.quick_combo.setCurrentIndex(1)
        assert vp.PRESET_LABEL in pipe.library_label.text() and "Not manufacturer data" in pipe.library_label.text()
        pipe.length.setValue(100)
        pipe._save()
        assert pipe.result["legacy_preset"]["origin"] == vp.LEGACY_PRESET
        assert pipe.result["legacy_preset"]["table"] == "pipe_db"
        # the first entry's 6.65 lb/ft lands as 6.7 in the 1-decimal input: recorded, not hidden
        assert pipe.result["legacy_preset"]["table_values"]["weight"] == 6.65
        assert pipe.result["legacy_preset"]["values"]["weight"] == pytest.approx(6.7)
        pipe.weight.setValue(pipe.weight.value() + 1)              # edited -> no longer the preset
        pipe._save()
        assert "legacy_preset" not in pipe.result

        casing.type_combo.setCurrentIndex(1)
        casing.quick_combo.setCurrentIndex(1)
        assert vp.PRESET_LABEL in casing.preset_label.text()
        casing.to_md.setValue(500)
        casing._save()
        assert casing.result.get("legacy_preset", {}).get("table") == "casing_db"
    finally:
        pipe.deleteLater()
        casing.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_w3b_template_is_labelled_until_replaced_from_the_library(w3b):
    tab, db, _ids = w3b
    tab.schematic = wa.to_schematic([])
    tab._sync_tables_to_schematic()
    assert all(vp.PRESET_LABEL in tab._casing_add_combo.itemText(i) for i in range(tab._casing_add_combo.count()))
    tab._casing_add_combo.setCurrentIndex(1)
    tab._add_casing_from_combo()
    assert tab.casing_table.item(0, 6).text() == vp.PRESET_LABEL
    assert "MANUFACTURER" not in json.dumps(sd.casing_origins(tab.schematic.casings[0]))
    doc = sd.to_document(tab.schematic, well_id=tab.current_well_id)
    assert doc["casings"][0]["legacy_preset"]["table"] == "w3b_casing_templates"
    assert doc["casings"][0]["field_origins"]["od_in"] == vp.LEGACY_PRESET
    tab.casing_table.item(0, 1).setText("13.5")                      # edited -> typed, the preset no longer holds
    assert tab.casing_table.item(0, 6).text() == "typed (template edited)"
    assert sd.to_document(tab.schematic, well_id=1)["casings"][0]["legacy_preset"] is None
    assert tab.apply_library_to_casing(0, snap(db, "SYN-CSG-96"))
    assert tab.schematic.casings[0].legacy_preset is None
    assert tab.casing_table.item(0, 6).text().startswith("Library SYN library v1")


# ---------------------------------------------------------------- M207 versioned document
def test_document_round_trip_keeps_binding_preset_and_missing_values(env):
    db, _ids = env
    schematic = wa.to_schematic(ARCH)
    schematic.casings[0].tubular_reference = rb.make_binding(snap(db, "SYN-CSG-NOWT"), rb.ARCHITECTURE_FIELDS)
    (schematic.casings[0].od_inch, schematic.casings[0].id_inch, schematic.casings[0].weight_ppf,
     schematic.casings[0].grade) = 7.013, 6.211, None, ""
    text = sd.dumps(schematic, well_id=11)
    doc = json.loads(text)
    assert doc["schema"] == sd.SCHEMA and doc["well_id"] == 11
    assert doc["casings"][0]["library"]["set_name"] == "SYN library"
    assert doc["casings"][0]["library"]["set_fingerprint"] and doc["casings"][0]["library"]["item_fingerprint"]
    back, report = sd.loads(text, expected_well_id=11)
    assert not report["legacy"] and not report["foreign"]
    assert back.casings[0].tubular_reference == schematic.casings[0].tubular_reference
    assert back.casings[0].weight_ppf is None
    assert [c.weight_ppf for c in back.casings] == [c.weight_ppf for c in schematic.casings]
    assert sd.dumps(back, well_id=11) == text


def test_legacy_documents_stay_readable_with_unknown_weight():
    legacy = {"casings": [{"name": "Surface", "type": "surface_casing", "od": 13.375, "id": None, "top": 0,
                           "bottom": 500, "cement_top": 200, "cement_bottom": 500}],
              "formations": [], "completion": [], "config": {"total_depth": 2000, "well_name": "SYN"}}
    schematic, report = sd.loads(json.dumps(legacy), expected_well_id=5, stored_well_id=5)
    assert report["legacy"] and schematic.casings[0].weight_ppf is None
    assert schematic.casings[0].value_source == vp.UNKNOWN_DEFAULT_LABEL
    assert schematic.casings[0].show_cement


def test_another_wells_document_is_refused_unless_confirmed_and_tampered_bindings_are_dropped(env):
    db, _ids = env
    schematic = wa.to_schematic(ARCH)
    schematic.casings[0].tubular_reference = rb.make_binding(snap(db, "SYN-CSG-96"), rb.ARCHITECTURE_FIELDS)
    (schematic.casings[0].od_inch, schematic.casings[0].id_inch, schematic.casings[0].weight_ppf,
     schematic.casings[0].grade) = 9.611, 8.703, 46.1, "SYN-80"
    text = sd.dumps(schematic, well_id=1)
    with pytest.raises(sd.SchematicOwnershipError, match="belongs to well id 1"):
        sd.loads(text, expected_well_id=2)
    _s, report = sd.loads(text, expected_well_id=2, accept_foreign=True)
    assert report["foreign"] and report["owner_well_id"] == 1
    doc = json.loads(text)
    doc["casings"][0]["tubular_reference"]["snapshot"]["spec"]["weight_ppf"] = 99.0
    back, report = sd.loads(json.dumps(doc), expected_well_id=1)
    assert report["dropped_bindings"] == [schematic.casings[0].name] and back.casings[0].tubular_reference is None
    with pytest.raises(sd.SchematicDocumentError, match="Unsupported"):
        sd.loads(json.dumps({"schema": "drillmaster-schematic-v99"}), expected_well_id=1)
    with pytest.raises(sd.SchematicOwnershipError):
        sd.loads(json.dumps({"schema": sd.SCHEMA, "casings": []}), expected_well_id=1)


def test_w3b_save_reload_export_and_cross_well_import(w3b, tmp_path):
    tab, db, ids = w3b
    tab.schematic = wa.to_schematic(ARCH)
    tab._sync_tables_to_schematic()
    assert tab.apply_library_to_casing(0, snap(db, "SYN-CSG-NOWT"))
    tab.show_success = tab.show_error = lambda *a, **k: None
    assert tab.save_data()
    stored = json.loads(db.get_wellbore_schematic(well_id=ids["A"][0])["elements_json"])
    assert stored["schema"] == sd.SCHEMA and stored["casings"][0]["weight_ppf"] is None
    tab.schematic = wa.to_schematic([])
    assert tab.load_saved_schematic()
    assert tab.schematic.casings[0].tubular_reference is not None and tab.schematic.casings[0].weight_ppf is None
    assert tab.casing_table.item(0, 5).text() == "—"

    path = tmp_path / "a.json"
    tab.export_schematic_json(str(path))
    tab.current_well_id = ids["B"][0]                              # another well is selected
    before = list(tab.schematic.casings)
    tab.schematic.casings = []
    assert not tab.import_schematic_json(str(path), confirm_foreign=lambda owner: False)
    assert tab.schematic.casings == [] and "belongs to well id" in tab.canvas_status.text()
    assert not tab.load_saved_schematic()                          # nothing saved for well B
    assert tab.import_schematic_json(str(path), confirm_foreign=lambda owner: owner == ids["A"][0])
    assert len(tab.schematic.casings) == len(before) and tab.last_document_report["foreign"]
    assert "imported from well id" in tab.canvas_status.text()


def _cement_doc(**cement):
    row = {"name": "SYN csg", "type": "casing", "od": 9.611, "id": 8.703, "top": 0.0, "bottom": 1000.0,
           "weight_ppf": 46.1, **cement}
    return json.dumps({"schema": sd.SCHEMA, "well_id": 1, "casings": [row]})


@pytest.mark.parametrize("cement", [
    {"show_cement": True, "cement_bottom": 1000.0},                       # top missing
    {"show_cement": True, "cement_top": 400.0},                           # bottom missing
    {"show_cement": True},                                                # whole interval missing
    {"show_cement": True, "cement_top": 900.0, "cement_bottom": 500.0},   # top below bottom
])
def test_d73_a_missing_cement_interval_is_reported_never_read_as_cement_to_surface(cement):
    schematic, report = sd.loads(_cement_doc(**cement), expected_well_id=1)
    casing = schematic.casings[0]
    assert casing.show_cement is False
    assert any("cement interval" in m for m in report["missing"]), report["missing"]
    assert [c for c in wa.from_schematic(schematic) if c["kind"] == "cement"] == []   # nothing reaches a worksheet


def test_d73_a_known_cement_interval_including_cement_to_surface_is_kept():
    schematic, report = sd.loads(_cement_doc(show_cement=True, cement_top=0.0, cement_bottom=1000.0),
                                 expected_well_id=1)
    assert schematic.casings[0].show_cement is True and not any("cement" in m for m in report["missing"])
    cement = [c for c in wa.from_schematic(schematic) if c["kind"] == "cement"]
    assert [(c["top_md"], c["bottom_md"]) for c in cement] == [(0.0, 1000.0)]        # an entered 0 stays 0
    schematic, _report = sd.loads(_cement_doc(cement_top=500.0, cement_bottom=1000.0), expected_well_id=1)
    assert schematic.casings[0].show_cement is True                                 # default: shown when known
