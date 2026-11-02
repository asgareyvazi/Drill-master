"""M88: survey and architecture revisions in the unified history, recalculation and lineage.

The survey golden is hand-derived (vertical hold + one circular arc), not produced by the code
under test. Tampering is simulated past the immutability triggers, as in M85.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import calculation_history as ch  # noqa: E402
from core import survey_revisions as sr  # noqa: E402
from core import well_architecture as wa  # noqa: E402
from core.calculation_cases import save_case  # noqa: E402
from tests.test_m70_integrity import _open, _seed  # noqa: E402
from tests.test_m74_well_architecture import ARCH  # noqa: E402

J = [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": 300.0, "inc": 0.0, "azi": 0.0},
     {"md": 600.0, "inc": 30.0, "azi": 0.0}]
R = 300.0 / math.radians(30.0)                     # build radius of the 300 m arc, 0 -> 30 deg
GOLDEN_TVD = 300.0 + R * math.sin(math.radians(30.0))
GOLDEN_NORTH = R * (1.0 - math.cos(math.radians(30.0)))


@pytest.fixture
def env(tmp_path, monkeypatch):
    path = tmp_path / "m88.sqlite"
    manager = _open(path, tmp_path, monkeypatch)
    ids = _seed(manager)
    yield manager, path, ids
    manager.close()


def _survey(manager, well, **kw):
    kw.setdefault("depth_datum", "RKB")
    kw.setdefault("azimuth_reference", "true")
    return sr.save_revision(manager, well, J, **kw)


def _entry(manager, key, well=None):
    entries = ch.load_history(manager, well_id=well)
    return next(e for e in entries if e.key == key)


def _tamper(manager, path, trigger_prefix, sql, params):
    manager.close()
    with sqlite3.connect(path) as con:
        for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE ?",
                                   (f"{trigger_prefix}%",)).fetchall():
            con.execute(f"DROP TRIGGER {name}")
        con.execute(sql, params)
    manager.initialize()


def test_revision_sources_are_listed_counted_and_filtered(env):
    manager, _path, ids = env
    well = ids["A"][0]
    survey = _survey(manager, well, source_type="manual")
    wa.save_revision(manager, well, ARCH, survey_revision_id=survey["id"], note="SYN base design")
    assert {"Survey revision", "Well architecture"} <= set(ch.SOURCES)
    assert ch.count_history(manager, well_id=well, sources=["Survey revision"]) == 1
    assert ch.count_history(manager, well_id=well, sources=["Well architecture"]) == 1
    # the architecture table has no method column: the text filter uses the schema version and the note
    assert ch.count_history(manager, well_id=well, text="m74 well architecture") == 1
    assert ch.count_history(manager, well_id=well, text="base design") == 1
    assert ch.count_history(manager, well_id=well, text="minimum curvature") == 1
    assert ch.count_history(manager, well_id=well, text="nothing like this") == 0
    assert ch.count_history(manager, well_id=ids["B"][0]) == 0           # no leakage to another well


def test_survey_entry_headline_matches_the_independent_golden(env):
    manager, _path, ids = env
    rev = _survey(manager, ids["A"][0], wellbore_id=ids["A"][1])
    entry = _entry(manager, f"survey_revisions:{rev['id']}")
    assert entry.scope.startswith("SURVEY") and entry.wellbore_id == ids["A"][1]
    assert entry.results["integrity"] == "VERIFIED"
    assert entry.results["td_tvd"] == pytest.approx(GOLDEN_TVD, abs=1e-6)
    assert entry.results["td_north"] == pytest.approx(GOLDEN_NORTH, abs=1e-6)
    assert entry.results["td_east"] == pytest.approx(0.0, abs=1e-9)
    assert ch.entry_status(entry)["reproducible"] == "REPRODUCIBLE"


def test_survey_recalculation_is_stored_as_a_new_linked_case(env):
    manager, _path, ids = env
    rev = _survey(manager, ids["A"][0])
    entry = _entry(manager, f"survey_revisions:{rev['id']}")
    outcome = ch.recalculate_entry(entry)
    assert outcome["status"] == "MATCH" and outcome["method_matches"] is True
    assert outcome["values"]["td_tvd"] == pytest.approx(GOLDEN_TVD, abs=1e-6)
    case = ch.save_recalculation(manager, entry, outcome)
    links = ch.lineage(manager, entry)
    assert any(item["key"] == f"calculation_cases:{case['id']}" and item["direction"] == "derived" for item in links)
    assert sr.get_revision(manager, rev["id"])["stations_sha256"] == rev["stations_sha256"]   # original untouched


def test_tampered_survey_stations_are_unreadable_and_cannot_be_stored(env):
    manager, path, ids = env
    rev = _survey(manager, ids["A"][0])
    bad = [dict(s) for s in J]
    bad[-1]["inc"] = 31.0
    _tamper(manager, path, "trg_survey_revision_immutable", "UPDATE survey_revisions SET stations_json=? WHERE id=?",
            (json.dumps(bad), rev["id"]))
    entry = _entry(manager, f"survey_revisions:{rev['id']}")
    assert entry.results["integrity"] == "HASH MISMATCH"
    outcome = ch.recalculate_entry(entry)
    assert outcome["status"] == "UNREADABLE" and outcome["values"] == {}
    with pytest.raises(ValueError, match="Nothing to store"):
        ch.save_recalculation(manager, entry, outcome)


def test_altered_stored_survey_positions_are_different(env):
    manager, path, ids = env
    rev = _survey(manager, ids["A"][0])
    positions = sr.get_revision(manager, rev["id"])["results"]
    positions[-1]["tvd"] += 0.5
    _tamper(manager, path, "trg_survey_revision_immutable", "UPDATE survey_revisions SET results_json=? WHERE id=?",
            (json.dumps(positions), rev["id"]))
    outcome = ch.recalculate_entry(_entry(manager, f"survey_revisions:{rev['id']}"))
    assert outcome["status"] == "DIFFERENT"
    assert outcome["values"]["max_position_difference_m"] == pytest.approx(0.5, abs=1e-6)


def test_architecture_recalculation_hash_and_validation_drift(env):
    manager, path, ids = env
    arch = wa.save_revision(manager, ids["A"][0], ARCH)
    key = f"well_architecture_revisions:{arch['id']}"
    entry = _entry(manager, key)
    assert entry.results["integrity"] == "VERIFIED" and entry.results["errors"] == 0
    outcome = ch.recalculate_entry(entry)
    assert outcome["status"] == "MATCH" and outcome["method_matches"] is True
    assert outcome["values"]["components"] == len(arch["components"])
    # stored validation altered -> DIFFERENT (the components and their hash are intact)
    _tamper(manager, path, "trg_well_architecture_immutable",
            "UPDATE well_architecture_revisions SET validation_json=? WHERE id=?",
            (json.dumps({"errors": [], "warnings": ["SYN injected warning"]}), arch["id"]))
    assert ch.recalculate_entry(_entry(manager, key))["status"] == "DIFFERENT"
    # components altered -> the hash fails -> UNREADABLE, nothing re-validated
    _tamper(manager, path, "trg_well_architecture_immutable",
            "UPDATE well_architecture_revisions SET components_json=? WHERE id=?",
            (json.dumps(arch["components"][:-1]), arch["id"]))
    entry = _entry(manager, key)
    assert entry.results["integrity"] == "HASH MISMATCH"
    assert ch.recalculate_entry(entry)["status"] == "UNREADABLE"


def test_lineage_follows_revision_chains_and_the_architecture_survey_link(env):
    manager, _path, ids = env
    well = ids["A"][0]
    s1 = _survey(manager, well)
    s2 = sr.transform_revision(manager, s1["id"], "grid", convergence_deg=0.5, parameter_source="SYN CRS note")
    a1 = wa.save_revision(manager, well, ARCH)
    a2 = wa.save_revision(manager, well, ARCH, parent_id=a1["id"], survey_revision_id=s2["id"])
    keys = lambda key: {(i["direction"], i["key"]) for i in ch.lineage(manager, _entry(manager, key))}  # noqa: E731
    assert keys(f"survey_revisions:{s2['id']}") >= {
        ("parent", f"survey_revisions:{s1['id']}"), ("used_by", f"well_architecture_revisions:{a2['id']}")}
    assert ("child", f"survey_revisions:{s2['id']}") in keys(f"survey_revisions:{s1['id']}")
    assert keys(f"well_architecture_revisions:{a2['id']}") >= {
        ("parent", f"well_architecture_revisions:{a1['id']}"), ("uses", f"survey_revisions:{s2['id']}")}
    assert ("child", f"well_architecture_revisions:{a2['id']}") in keys(f"well_architecture_revisions:{a1['id']}")
    c1 = save_case(manager, calculator="SYN", name="first", inputs={"a": 1}, results={"b": 2}, method="m",
                   method_version="v", well_id=well)
    c2 = save_case(manager, calculator="SYN", name="second", inputs={"a": 1}, results={"b": 2}, method="m",
                   method_version="v", well_id=well, parent_id=c1["id"])
    assert ("parent", f"calculation_cases:{c1['id']}") in keys(f"calculation_cases:{c2['id']}")
    assert ("child", f"calculation_cases:{c2['id']}") in keys(f"calculation_cases:{c1['id']}")


def test_history_tab_opens_a_linked_record_on_another_page(env, monkeypatch):
    from PySide6 import QtWidgets
    from tabs import calculation_history_tab as tab_module

    manager, _path, ids = env
    well = ids["A"][0]
    s1 = _survey(manager, well)
    for n in range(5):                                  # newer records push s1 to the last page
        save_case(manager, calculator="SYN", name=f"filler {n}", inputs={"a": n}, results={"b": n}, method="m",
                  method_version="v", well_id=well)
    arch = wa.save_revision(manager, well, ARCH, survey_revision_id=s1["id"])
    monkeypatch.setattr(tab_module, "PAGE_SIZE", 2)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tab = tab_module.CalculationHistoryTab(db_manager=manager)
    try:
        tab.set_well(well)
        assert tab.page == 0 and tab.page_label.text() == "Page 1 of 4"
        row = next(i for i, e in enumerate(tab.entries) if e.key == f"well_architecture_revisions:{arch['id']}")
        tab.select_rows([row])
        labels = [tab.lineage_combo.itemText(i) for i in range(tab.lineage_combo.count())]
        assert f"Uses: survey revision id {s1['id']}" in labels
        tab.lineage_combo.setCurrentIndex(labels.index(f"Uses: survey revision id {s1['id']}"))
        assert tab.open_linked() is True
        assert tab.page == 3 and tab.selected()[0].key == f"survey_revisions:{s1['id']}"
        tab.recalculate()
        assert tab.last_outcome["status"] == "MATCH"
        case = tab.save_recalculation()
        assert case and case["id"]
        assert ch.lineage(manager, _entry(manager, f"survey_revisions:{s1['id']}"))[0]["key"] == \
            f"calculation_cases:{case['id']}"
    finally:
        tab.deleteLater()
        app.processEvents()
