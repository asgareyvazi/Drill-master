"""M85: survey reference declaration, explicit azimuth conversion and revision integrity.

Goldens are hand-derived (closed-form arc/line geometry), not produced by the code under test.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import survey_revisions as sr  # noqa: E402
from core.authorization import AuthorizationError  # noqa: E402
from tests.test_m70_integrity import _open, _seed  # noqa: E402

MAG = [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": 300.0, "inc": 0.0, "azi": 0.0},
       {"md": 600.0, "inc": 20.0, "azi": 357.0}, {"md": 900.0, "inc": 35.0, "azi": 10.0}]


@pytest.fixture
def env(tmp_path, monkeypatch):
    path = tmp_path / "m85.sqlite"
    manager = _open(path, tmp_path, monkeypatch)
    ids = _seed(manager)
    yield manager, path, ids
    manager.close()


def _magnetic(manager, ids):
    return sr.save_revision(manager, ids["A"][0], MAG, depth_datum="RKB", azimuth_reference="magnetic")


# ---- independent minimum-curvature benchmarks ----------------------------------------------------
def _last(stations):
    return sr.compute(stations)[-1]


def test_minimum_curvature_closed_form_benchmarks():
    # vertical
    v = _last([{"md": 0, "inc": 0, "azi": 0}, {"md": 250, "inc": 0, "azi": 0}])
    assert (v["tvd"], v["north"], v["east"]) == pytest.approx((250.0, 0.0, 0.0), abs=1e-9)
    # straight hold: inc 30, azi 45 over 100 m
    h = _last([{"md": 0, "inc": 30, "azi": 45}, {"md": 100, "inc": 30, "azi": 45}])
    assert h["tvd"] == pytest.approx(100 * math.cos(math.radians(30)), abs=1e-9)
    assert h["north"] == pytest.approx(50 / math.sqrt(2), abs=1e-9)
    assert h["east"] == pytest.approx(50 / math.sqrt(2), abs=1e-9)
    # build arc in a vertical plane: 0 -> 30 deg over 300 m (R = L / theta)
    radius = 300 / math.radians(30)
    b = _last([{"md": 0, "inc": 0, "azi": 0}, {"md": 300, "inc": 30, "azi": 0}])
    assert b["tvd"] == pytest.approx(radius * math.sin(math.radians(30)), abs=1e-6)
    assert b["north"] == pytest.approx(radius * (1 - math.cos(math.radians(30))), abs=1e-6)
    assert b["dls"] == pytest.approx(3.0, abs=1e-9)                 # deg/30 m
    # horizontal quarter turn at inc 90: azi 0 -> 90 over L, R = L / (pi/2)
    t = _last([{"md": 0, "inc": 90, "azi": 0}, {"md": 157.07963267949, "inc": 90, "azi": 90}])
    assert (t["tvd"], t["north"], t["east"]) == pytest.approx((0.0, 100.0, 100.0), abs=1e-6)
    # azimuth wrap 350 -> 10 behaves as a 20 deg turn symmetric about north
    w = _last([{"md": 0, "inc": 90, "azi": 350}, {"md": 100, "inc": 90, "azi": 10}])
    assert w["east"] == pytest.approx(0.0, abs=1e-9) and w["north"] > 99.0
    # tiny dogleg: ratio factor -> 1 (no division blow-up)
    s = _last([{"md": 0, "inc": 10, "azi": 0}, {"md": 10.0, "inc": 10.0000001, "azi": 0}])
    assert math.isfinite(s["tvd"]) and s["tvd"] == pytest.approx(10 * math.cos(math.radians(10)), rel=1e-7)
    assert s["north"] == pytest.approx(10 * math.sin(math.radians(10)), rel=1e-7)


# ---- reference must be declared --------------------------------------------------------------------
def test_reference_is_never_assumed(env):
    manager, _path, ids = env
    assert "Declare the azimuth reference" in sr.preview(MAG, depth_datum="RKB").errors[0]
    with pytest.raises(sr.SurveyRevisionError, match="azimuth reference"):
        sr.save_revision(manager, ids["A"][0], MAG, depth_datum="RKB")
    with pytest.raises(TypeError):
        sr.snapshot_survey_points(manager, ids["A"][0], depth_datum="RKB")   # keyword is required


# ---- conversion conventions (hand values) -----------------------------------------------------------
@pytest.mark.parametrize("src, dst, dec, conv, expected", [
    ("magnetic", "true", 5.0, None, 5.0),        # mag 10 + dec 5 -> true 15
    ("grid", "true", None, 3.0, 3.0),            # grid 350 + conv 3 -> true 353
    ("true", "grid", None, 5.0, -5.0),           # true 2 -> grid 357
    ("magnetic", "grid", 4.0, 1.5, 2.5),         # grid = mag + dec - conv
    ("true", "magnetic", -7.25, None, 7.25),     # west declination
])
def test_azimuth_correction_conventions(src, dst, dec, conv, expected):
    assert sr.azimuth_correction(src, dst, declination_deg=dec, convergence_deg=conv) == pytest.approx(expected)


@pytest.mark.parametrize("kwargs, message", [
    ({"declination_deg": None}, "needs the declination"),
    ({"declination_deg": float("nan")}, "needs the declination"),
    ({"declination_deg": 200.0}, "outside the accepted range"),
    ({"parameter_source": "  "}, "comes from"),
    ({"reference_date": ""}, "give the date"),
])
def test_conversion_refusals_save_nothing(env, kwargs, message):
    manager, _path, ids = env
    rev = _magnetic(manager, ids)
    args = {"declination_deg": 4.5, "parameter_source": "SYN survey contractor sheet",
            "reference_date": "2026-10-01", **kwargs}
    with pytest.raises(sr.SurveyRevisionError, match=message):
        sr.transform_revision(manager, rev["id"], "true", **args)
    with pytest.raises(sr.SurveyRevisionError, match="already uses"):
        sr.transform_revision(manager, rev["id"], "magnetic", declination_deg=1, parameter_source="x",
                              reference_date="2026-01-01")
    with pytest.raises(sr.SurveyRevisionError, match="grid convergence"):
        sr.transform_revision(manager, rev["id"], "grid", declination_deg=4.5, parameter_source="x",
                              reference_date="2026-01-01")
    assert len(sr.list_revisions(manager, ids["A"][0])) == 1


def test_conversion_creates_a_linked_revision_and_rotates_positions(env):
    manager, _path, ids = env
    source = _magnetic(manager, ids)
    new = sr.transform_revision(manager, source["id"], "true", declination_deg=4.5,
                                parameter_source="SYN survey contractor sheet", reference_date="2026-10-01",
                                note="SYN")
    assert new["revision"] == 2 and new["parent_id"] == source["id"] and new["mode"] == "azimuth_transform"
    assert new["azimuth_reference"] == "true" and new["depth_datum"] == "RKB" and new["integrity"] == "VERIFIED"
    assert [s["azi"] for s in new["stations"]] == pytest.approx([4.5, 4.5, 1.5, 14.5])   # 357 + 4.5 wraps
    meta = json.loads(new["source_ref"])
    assert meta["from"] == "magnetic" and meta["to"] == "true" and meta["declination_deg"] == 4.5
    assert meta["convergence_deg"] is None and meta["method_version"] == sr.TRANSFORM_VERSION
    assert meta["source_stations_sha256"] == source["stations_sha256"] and meta["reference_date"] == "2026-10-01"
    # a uniform azimuth shift rotates the horizontal plane; TVD is unchanged (independent check)
    c, s = math.cos(math.radians(4.5)), math.sin(math.radians(4.5))
    for old, rot in zip(source["results"], new["results"]):
        assert rot["tvd"] == pytest.approx(old["tvd"], abs=1e-6)
        assert rot["north"] == pytest.approx(old["north"] * c - old["east"] * s, abs=1e-6)
        assert rot["east"] == pytest.approx(old["north"] * s + old["east"] * c, abs=1e-6)
    again = sr.get_revision(manager, source["id"])
    assert again["stations"] == source["stations"] and again["azimuth_reference"] == "magnetic"
    assert sr.verify_results(new)["status"] == "MATCH"
    assert not sr.compare_revisions(source, new)["comparable"]
    # grid conversion of the converted revision needs only the convergence (no declination)
    grid = sr.transform_revision(manager, new["id"], "grid", convergence_deg=-1.25,
                                 parameter_source="SYN CRS report")
    assert grid["stations"][0]["azi"] == pytest.approx(5.75) and json.loads(grid["source_ref"])["declination_deg"] is None


def test_station_hash_is_verified_on_read_and_blocks_conversion(env):
    manager, path, ids = env
    rev = _magnetic(manager, ids)
    manager.close()
    with sqlite3.connect(path) as con:   # simulate out-of-band tampering past the immutability trigger
        for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='trigger' "
                                   "AND name LIKE 'trg_survey_revision_immutable%'").fetchall():
            con.execute(f"DROP TRIGGER {name}")
        tampered = [dict(s) for s in MAG]
        tampered[-1]["azi"] = 11.0
        con.execute("UPDATE survey_revisions SET stations_json=? WHERE id=?", (json.dumps(tampered), rev["id"]))
    manager.initialize()
    bad = sr.get_revision(manager, rev["id"])
    assert bad["integrity"] == "HASH MISMATCH"
    assert sr.list_revisions(manager, ids["A"][0])[0]["integrity"] == "HASH MISMATCH"
    assert sr.verify_results(bad)["status"] == "DIFFERENT"
    with pytest.raises(sr.SurveyRevisionError, match="hash check"):
        sr.tie_in_from_revision(bad)
    with pytest.raises(sr.SurveyRevisionError, match="hash check"):
        sr.transform_revision(manager, rev["id"], "true", declination_deg=1, parameter_source="x",
                              reference_date="2026-01-01")


def test_a_viewer_cannot_save_a_conversion(env, tmp_path, monkeypatch):
    manager, path, ids = env
    rev = _magnetic(manager, ids)
    manager.close()
    viewer = _open(path, tmp_path, monkeypatch, principal="viewer")
    try:
        with pytest.raises(AuthorizationError):
            sr.transform_revision(viewer, rev["id"], "true", declination_deg=4.5, parameter_source="x",
                                  reference_date="2026-01-01")
        assert len(sr.list_revisions(viewer, ids["A"][0])) == 1
    finally:
        viewer.close()


# ---- desktop panel -----------------------------------------------------------------------------------
def test_panel_requires_declaration_and_converts_with_explicit_values(env):
    from PySide6 import QtWidgets
    from tabs.survey_revision_panel import SurveyRevisionPanel
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    manager, _path, ids = env
    manager.save_survey_points([dict(s, well_id=ids["A"][0]) for s in MAG])
    panel = SurveyRevisionPanel(manager)
    try:
        panel.set_well(ids["A"][0])
        panel.datum_edit.setText("RKB")
        assert panel.azimuth_combo.currentData() == ""
        assert panel.freeze_current() is None and "azimuth reference" in panel.status.text()
        panel.azimuth_combo.setCurrentIndex(panel.azimuth_combo.findData("magnetic"))
        assert panel.freeze_current()["azimuth_reference"] == "magnetic"
        assert panel.table.item(0, sr_col("Station hash")).text() == "VERIFIED"
        assert not panel.convert_btn.isEnabled()
        panel.table.selectRow(0)
        assert panel.convert_btn.isEnabled()
        panel.target_combo.setCurrentIndex(panel.target_combo.findData("true"))
        panel.declination_edit.setText("4.5")
        panel.param_source_edit.setText("SYN contractor sheet")
        assert panel.convert_selected() is None and "give the date" in panel.status.text()
        panel.declination_edit.setText("east")
        panel.param_date_edit.setText("2026-10-01")
        assert panel.convert_selected() is None and "not a number" in panel.status.text()
        panel.declination_edit.setText("4.5")
        panel.table.selectRow(0)
        new = panel.convert_selected()
        assert new["azimuth_reference"] == "true" and "Converted into survey revision 2" in panel.status.text()
        assert panel.table.rowCount() == 2
    finally:
        panel.deleteLater()
        app.processEvents()


def sr_col(name):
    from tabs.survey_revision_panel import COLUMNS
    return COLUMNS.index(name)
