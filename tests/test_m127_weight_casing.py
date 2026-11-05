"""M127: the W13 Weight page (weight card + soft-string T&D on a PINNED survey revision) and Casing Strength
(API TR 5C3 pipe-body subset with per-field provenance and the architecture pin) are re-runnable contracts.

T&D no longer reads the Multi-Survey table (``dd_surveys``) of another page: the user picks a survey revision of
the selected well, its stations are pinned with the revision identity and station SHA-256, and a re-run checks
that hash. Goldens are independent closed forms written out here (weight card, vertical and straight inclined
soft-string, Barlow burst, pipe-body yield). Synthetic data only; offscreen Qt.
"""
from __future__ import annotations

import json
import math
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6 import QtWidgets  # noqa: E402

from core import calculation_history as ch  # noqa: E402
from core import calculator_contracts as contracts  # noqa: E402
from core import survey_revisions as sr  # noqa: E402
from core import w13_weight  # noqa: E402
from core import well_architecture as wa  # noqa: E402
from tests.test_m70_integrity import _open, _seed  # noqa: E402
from tests.test_m74_well_architecture import ARCH  # noqa: E402

FT = 3.28084
PIPES = [{"type": "DP", "od": 5.0, "id": 4.276, "length": 2800.0, "weight": 19.5},
         {"type": "DC", "od": 6.5, "id": 2.8125, "length": 200.0, "weight": 92.0}]
VERTICAL = [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": 1500.0, "inc": 0.0, "azi": 0.0},
            {"md": 3000.0, "inc": 0.0, "azi": 0.0}]
SLANT = [{"md": 0.0, "inc": 30.0, "azi": 0.0}, {"md": 1500.0, "inc": 30.0, "azi": 0.0},
         {"md": 3000.0, "inc": 30.0, "azi": 0.0}]


@pytest.fixture
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def env(tmp_path, monkeypatch):
    manager = _open(tmp_path / "m127.sqlite", tmp_path, monkeypatch)
    ids = _seed(manager)
    yield manager, ids
    manager.close()


@pytest.fixture
def w13(app, env, monkeypatch):
    from PySide6.QtCore import QCoreApplication, QEvent

    from tabs import w13_Engineering_Calculator as w13_module
    manager, ids = env
    monkeypatch.setattr(w13_module.QMessageBox, "information", lambda *a, **k: None)
    tab = w13_module.EngineeringCalculatorTab(manager)
    tab.on_well_changed(ids["A"][0], {"name": "SYN-A"})
    yield tab
    tab.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def _value(case, field_id):
    return next(v["value"] for v in case["results"].values() if isinstance(v, dict) and v.get("field_id") == field_id)


def _case_entry(db, case_id):
    return next(e for e in ch.load_history(db, sources=["Calculation case"]) if e.record_id == case_id)


def _buoyed_ppf(ppf, mw_pcf):
    return ppf * (1.0 - (mw_pcf / 7.48) / 65.5)


# ---- method goldens -----------------------------------------------------------------------------------
def test_weight_card_matches_the_closed_form():
    values = {"pipes": PIPES, "mw": 75.0, "inclination": 30.0, "tds": 40.0, "friction": 0.25, "hole_id": 0.0,
              "wob": 0.0, "survey": None}
    out = w13_weight.results(values)
    air = (2800 * 19.5 + 200 * 92.0) * FT
    bf = 1.0 - (75.0 / 7.48) / 65.5
    buoyed = air * math.cos(math.radians(30)) * bf
    drag = buoyed * 0.25 * math.sin(math.radians(30))
    assert out["air_weight_klbf"] == pytest.approx(air / 1000, rel=1e-9)
    assert out["buoyancy_factor"] == pytest.approx(bf, abs=1e-6)
    assert out["buoyed_weight_klbf"] == pytest.approx(buoyed / 1000, rel=1e-6)
    assert out["hook_load_klbf"] == pytest.approx(buoyed / 1000 + 40.0, rel=1e-6)
    assert out["pickup_klbf"] == pytest.approx((buoyed + drag) / 1000 + 40.0, rel=1e-6)
    assert out["slackoff_klbf"] == pytest.approx((buoyed - drag) / 1000 + 40.0, rel=1e-6)
    assert all(out[key] is None for key in w13_weight.TD_RESULTS)       # no pin: T&D UNKNOWN, never 0


def _pin(stations, revision_id=7, well_id=1):
    return {"revision_id": revision_id, "revision": 1, "well_id": well_id, "wellbore_id": None,
            "stations": [dict(s) for s in stations], "stations_sha256": sr.stations_sha256(stations)}


def test_soft_string_vertical_and_straight_inclined_goldens():
    base = {"pipes": PIPES, "mw": 75.0, "inclination": 0.0, "tds": 0.0, "friction": 0.25, "hole_id": 0.0,
            "wob": 0.0}
    weight_lbf = sum(_buoyed_ppf(p["weight"], 75.0) * p["length"] * FT for p in PIPES)
    vertical = w13_weight.results(dict(base, survey=_pin(VERTICAL)))
    for key in ("td_pickup_klbf", "td_slackoff_klbf", "td_rotating_klbf", "td_buoyed_weight_klbf"):
        assert vertical[key] == pytest.approx(weight_lbf / 1000, abs=0.011), key
    assert vertical["td_surface_torque_ft_lbf"] == pytest.approx(0.0, abs=0.06)
    # straight hole at 30 deg: Fn = w_b dL sin I per element; F = sum w_b dL (cos I +/- mu sin I); T = mu Fn r
    slant = w13_weight.results(dict(base, survey=_pin(SLANT)))
    c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
    assert slant["td_pickup_klbf"] == pytest.approx(weight_lbf * (c + 0.25 * s) / 1000, abs=0.011)
    assert slant["td_slackoff_klbf"] == pytest.approx(weight_lbf * (c - 0.25 * s) / 1000, abs=0.011)
    assert slant["td_rotating_klbf"] == pytest.approx(weight_lbf * c / 1000, abs=0.011)
    torque = sum(0.25 * _buoyed_ppf(p["weight"], 75.0) * p["length"] * FT * s * p["od"] / 24.0 for p in PIPES)
    assert slant["td_surface_torque_ft_lbf"] == pytest.approx(torque, abs=0.06)


def test_a_tampered_pin_is_refused():
    pin = _pin(VERTICAL)
    pin["stations"][1]["md"] = 1400.0
    with pytest.raises(w13_weight.SurveyPinError, match="SHA-256"):
        w13_weight.pin_stations(pin)
    with pytest.raises(ValueError, match="NOT REPRODUCIBLE"):
        contracts.WEIGHT.recalculate({"pipes": PIPES, "mw": 75.0, "inclination": 0.0, "tds": 0.0,
                                      "friction": 0.2, "hole_id": 0.0, "wob": 0.0, "survey": pin})


def test_pin_from_revision_checks_integrity_well_and_wellbore(env):
    manager, ids = env
    rev = sr.save_revision(manager, ids["A"][0], VERTICAL, wellbore_id=ids["A"][1], depth_datum="RKB",
                           azimuth_reference="true")
    record = sr.get_revision(manager, rev["id"])
    pin = w13_weight.pin_from_revision(record, well_id=ids["A"][0], wellbore_id=ids["A"][1])
    assert pin["revision_id"] == rev["id"] and pin["stations_sha256"] == record["stations_sha256"]
    assert pin["depth_datum"] == "RKB" and pin["azimuth_reference"] == "true"
    with pytest.raises(w13_weight.SurveyPinError, match="another well"):
        w13_weight.pin_from_revision(record, well_id=ids["B"][0])
    with pytest.raises(w13_weight.SurveyPinError, match="belongs to wellbore"):
        w13_weight.pin_from_revision(record, well_id=ids["A"][0], wellbore_id=ids["B"][1])
    with pytest.raises(w13_weight.SurveyPinError, match="No survey revision"):
        w13_weight.pin_from_revision(None, well_id=ids["A"][0])


# ---- Weight page --------------------------------------------------------------------------------------
def _fill_weight(w13):
    assert w13.calculator_finder.open_path("Weight")
    w13.wt_pipes[:] = [dict(p) for p in PIPES]
    w13._wt_refresh_table()
    w13.wt_mw.setValue(75.0)
    w13.wt_inc.setValue(0.0)
    w13.wt_tds.setValue(40.0)
    w13.wt_friction.setValue(0.25)
    w13.wt_wob.setValue(0.0)


def _choose(w13, revision_id):
    index = w13.wt_survey_combo.findData(revision_id)
    assert index > 0
    w13.wt_survey_combo.setCurrentIndex(index)
    w13._wt_select_survey(index)


def test_td_runs_only_on_the_pinned_revision_never_on_the_multi_survey_table(w13, env):
    manager, ids = env
    well = ids["A"][0]
    rev = sr.save_revision(manager, well, VERTICAL, depth_datum="RKB", azimuth_reference="true")
    sr.save_revision(manager, ids["B"][0], SLANT, depth_datum="RKB", azimuth_reference="true")
    w13.dd_surveys = [dict(s) for s in SLANT]                 # the other page's table must not be used
    _fill_weight(w13)
    w13._wt_reload_survey_revisions()
    listed = [w13.wt_survey_combo.itemData(i) for i in range(w13.wt_survey_combo.count())]
    assert listed == [None, rev["id"]]                         # only this well's revision
    w13._wt_calculate()
    assert w13.wt_td.text().startswith("NOT ASSESSED: select a survey revision") and w13._wt_last_td_run is None
    assert w13.wt_hl.text() != "" and "❌" not in w13.wt_hl.text()   # the weight card still works
    _choose(w13, rev["id"])
    w13._wt_calculate()
    weight = sum(_buoyed_ppf(p["weight"], 75.0) * p["length"] * FT for p in PIPES) / 1000
    run = w13._wt_last_td_run
    assert run["result_values"]["hookload_pickup"] == pytest.approx(weight, abs=0.011)   # vertical, not SLANT
    assert run["survey_source"]["revision_id"] == rev["id"] and f"survey rev {rev['revision']}" in w13.wt_td.text()
    w13._wt_save_calculation()
    entry = next(e for e in ch.load_history(manager, well_id=well, sources=["Torque & drag"]))
    assert entry.inputs["survey_source"]["stations_sha256"] == rev["stations_sha256"]
    assert ch.recalculate_entry(entry)["status"] == "MATCH"     # provenance never feeds reconstruction
    assert ("uses", f"survey_revisions:{rev['id']}") in {(i["direction"], i["key"]) for i in ch.lineage(manager, entry)}
    survey_entry = next(e for e in ch.load_history(manager, well_id=well, sources=["Survey revision"]))
    assert ("used_by", entry.key) in {(i["direction"], i["key"]) for i in ch.lineage(manager, survey_entry)}


def test_a_hash_mismatch_revision_cannot_be_pinned_and_a_well_change_drops_the_pin(w13, env):
    from core.database import SurveyRevision

    manager, ids = env
    good = sr.save_revision(manager, ids["A"][0], VERTICAL, depth_datum="RKB", azimuth_reference="true")
    bad = sr.save_revision(manager, ids["A"][0], SLANT, mode="replace", parent_id=good["id"], depth_datum="RKB",
                           azimuth_reference="true")
    results_only = sr.save_revision(manager, ids["A"][0], VERTICAL, mode="replace", parent_id=good["id"],
                                    depth_datum="RKB", azimuth_reference="true")
    with manager.engine.begin() as conn:                      # tamper behind the hash (trigger dropped as in M105)
        for (name,) in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger' "
                                            "AND name LIKE 'trg_survey_revision_immutable%'").fetchall():
            conn.exec_driver_sql(f"DROP TRIGGER {name}")
    with manager.session_scope() as session:
        row = session.get(SurveyRevision, bad["id"])
        stations = json.loads(row.stations_json)
        stations[1]["inc"] = 31.0
        row.stations_json = json.dumps(stations)
        other = session.get(SurveyRevision, results_only["id"])     # stations intact, stored results edited
        results = json.loads(other.results_json)
        results[-1]["tvd"] += 5.0
        other.results_json = json.dumps(results)
    _fill_weight(w13)
    w13._wt_reload_survey_revisions()
    index = w13.wt_survey_combo.findData(bad["id"])
    assert "HASH MISMATCH" in w13.wt_survey_combo.itemText(index)
    w13.wt_survey_combo.setCurrentIndex(index)
    w13._wt_select_survey(index)
    assert w13.wt_survey_pin is None and "station hash" in w13.wt_survey_label.text()
    assert w13.wt_survey_combo.currentIndex() == 0
    index = w13.wt_survey_combo.findData(results_only["id"])
    w13.wt_survey_combo.setCurrentIndex(index)
    w13._wt_select_survey(index)                              # the pin hash alone would not see this
    assert w13.wt_survey_pin is None and "stored results" in w13.wt_survey_label.text()
    _choose(w13, good["id"])
    assert w13.wt_survey_pin["revision_id"] == good["id"]
    w13.on_well_changed(ids["B"][0], {"name": "SYN-B"})
    assert w13.wt_survey_pin is None and w13.wt_survey_combo.count() == 1


def test_weight_case_pins_the_survey_reruns_reopens_and_detects_tampering(w13, env):
    manager, ids = env
    rev = sr.save_revision(manager, ids["A"][0], SLANT, depth_datum="RKB", azimuth_reference="true")
    _fill_weight(w13)
    w13._wt_reload_survey_revisions()
    _choose(w13, rev["id"])
    w13._wt_calculate()
    w13.case_bar.refresh()
    assert "Class: SCREENING CONTRACT" in w13.case_bar.contract_label.text()
    case = w13.case_bar.save_case("SYN weight")
    assert case["method_version"] == "M127 weight card and soft-string T&D v1"
    assert case["inputs"]["extra:survey"]["value"]["revision_id"] == rev["id"]
    assert _value(case, "td_pickup_klbf") == pytest.approx(w13._wt_last_td_run["result_values"]["hookload_pickup"])
    entry = _case_entry(manager, case["id"])
    assert entry.scope == "W13 CALCULATOR — SCREENING CONTRACT" and ch.recalculate_entry(entry)["status"] == "MATCH"
    assert ("uses", f"survey_revisions:{rev['id']}") in {(i["direction"], i["key"]) for i in ch.lineage(manager, entry)}
    # reopen into a cleared page restores the components and the pin
    w13.wt_pipes.clear()
    w13.wt_survey_pin = None
    assert w13.case_bar.reopen(case["id"]) == []
    assert w13.wt_pipes == PIPES and w13.wt_survey_pin["revision_id"] == rev["id"]
    assert "Restored from the case" in w13.wt_survey_label.text()
    # edited pinned stations are refused (not silently re-run), a changed component is DIFFERENT
    tampered = {k: (dict(v) if isinstance(v, dict) else v) for k, v in case["inputs"].items()}
    pin = json.loads(json.dumps(tampered["extra:survey"]["value"]))
    pin["stations"][2]["inc"] = 35.0
    tampered["extra:survey"] = dict(tampered["extra:survey"], value=pin)
    outcome = contracts.verify_case(case["method"], case["method_version"], tampered, case["results"])
    assert outcome["status"] == "UNREADABLE" and "SHA-256" in outcome["detail"]
    changed = {k: (dict(v) if isinstance(v, dict) else v) for k, v in case["inputs"].items()}
    changed["extra:pipes"] = dict(changed["extra:pipes"], value=[dict(PIPES[0], weight=21.9), PIPES[1]])
    outcome = contracts.verify_case(case["method"], case["method_version"], changed, case["results"])
    assert outcome["status"] == "DIFFERENT" and "td_pickup_klbf" in {d["field_id"] for d in outcome["differences"]}


def test_weight_case_without_a_pin_stores_unknown_td_and_matches(w13):
    _fill_weight(w13)
    w13._wt_calculate()
    case = w13.case_bar.save_case("SYN weight card only")
    assert case["method_version"] == "M127 weight card and soft-string T&D v1"
    assert _value(case, "td_pickup_klbf") is None and _value(case, "hook_load_klbf") is not None
    assert ch.recalculate_entry(_case_entry(w13.db, case["id"]))["status"] == "MATCH"


# ---- Casing Strength ----------------------------------------------------------------------------------
def test_casing_case_records_provenance_and_the_architecture_pin(w13, env):
    manager, ids = env
    arch = wa.save_revision(manager, ids["A"][0], ARCH, wellbore_id=ids["A"][1])
    assert w13.calculator_finder.open_path("CSG/CMT › Casing Strength")
    w13.load_casing_from_architecture("9-5/8 csg")
    # yield is unknown in the architecture: the page and the contract both refuse
    w13._csg_calc_strength()
    assert w13.csg_burst_res.text().startswith("Not calculated: yield strength unknown")
    case = w13.case_bar.save_case("SYN casing unknown yield")
    assert case["method_version"] != "M127 casing pipe-body strength v1" and "NOT ASSESSED" in case["note"]
    w13.csg_yield.setValue(80000.0)
    w13._csg_calc_strength()
    w13.case_bar.refresh()
    assert "Class: SCREENING CONTRACT" in w13.case_bar.contract_label.text()
    case = w13.case_bar.save_case("SYN casing")
    assert case["method_version"] == "M127 casing pipe-body strength v1"
    prov = case["inputs"]["extra:provenance"]["value"]
    assert prov["fields"] == {"od_in": "architecture", "id_in": "architecture", "wall_in": "derived",
                              "weight_ppf": "architecture", "yield_psi": "user"}
    assert prov["origin"]["architecture_revision_id"] == arch["id"] and "loaded" not in prov["origin"]
    wall = (9.625 - 8.681) / 2
    assert _value(case, "burst_rating_psi") == pytest.approx(0.875 * 2 * 80000 * wall / 9.625, abs=0.06)
    assert _value(case, "pipe_body_yield_lbf") == pytest.approx(80000 * math.pi / 4 * (9.625 ** 2 - 8.681 ** 2),
                                                                abs=0.6)
    assert _value(case, "burst_rating_psi") == pytest.approx(w13._csg_last_run["result_values"]["burst_rating_psi"])
    entry = _case_entry(manager, case["id"])
    assert ch.recalculate_entry(entry)["status"] == "MATCH"
    assert ("uses", f"well_architecture_revisions:{arch['id']}") in \
        {(i["direction"], i["key"]) for i in ch.lineage(manager, entry)}
    arch_entry = next(e for e in ch.load_history(manager, well_id=ids["A"][0], sources=["Well architecture"]))
    assert ("used_by", entry.key) in {(i["direction"], i["key"]) for i in ch.lineage(manager, arch_entry)}
    # reopen restores the origin: unchanged values keep their class, an edit becomes "user"
    w13._csg_reset_origin()
    assert w13.case_bar.reopen(case["id"]) == []
    assert w13.csg_provenance()["od_in"] == "architecture" and "restored case" in w13.csg_source_label.text()
    w13.csg_od.setValue(9.63)
    assert w13.csg_provenance()["od_in"] == "user"
    # a stored "unknown" required field or a missing provenance is never re-run
    bad = {k: (dict(v) if isinstance(v, dict) else v) for k, v in case["inputs"].items()}
    bad["extra:provenance"] = dict(bad["extra:provenance"], value={"origin": prov["origin"],
                                                                   "fields": dict(prov["fields"], yield_psi="unknown")})
    outcome = contracts.verify_case(case["method"], case["method_version"], bad, case["results"])
    assert outcome["status"] == "UNREADABLE" and "NOT ASSESSED" in outcome["detail"]
    bad["extra:provenance"] = dict(bad["extra:provenance"], value=None)
    outcome = contracts.verify_case(case["method"], case["method_version"], bad, case["results"])
    assert outcome["status"] == "UNREADABLE" and "provenance" in outcome["detail"]


def test_registry_after_m127():
    # M128: the registry-wide counts live in the latest milestone test (test_m128 / test_m125); this keeps
    # what M127 itself established
    assert contracts.classification_violations() == []
    for leaf in ("Weight", "CSG/CMT › Casing Strength"):
        assert leaf in contracts.CONTRACTS and leaf not in contracts.NOT_SUPPORTED
        assert contracts.leaf_class(leaf)[0] == contracts.CLASS_SCREENING
        assert contracts.CONTRACTS[leaf].method_version.startswith("M127")
