"""M140 adversarial audit: hostile inputs against the M121-M139 capabilities that the phase tests did not use.

Each test names the finding it pins (register: D54, D55, D56 in docs/engineering/PRODUCT_CAPABILITY_MATRIX.md).
Hand goldens, independent of the code: θ3 = 9, θ6 = 2 would give LSRYP 2·9 − 2 = 16, larger than either reading
(v1 replay only); bit cost 1000 + rig rate 24000 / 24 × (5 + 10) h = 16000 over 100 m = 160.00 per metre.
SYNTHETIC data only.
"""
from __future__ import annotations

import json
import math
import os
from datetime import date

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import bit_runs as br  # noqa: E402
from core import calculation_cases as cc  # noqa: E402
from core import calculation_history as ch  # noqa: E402
from core import mud_engineering as me  # noqa: E402
from core import npt_reconciliation as npt  # noqa: E402
from core import parameter_trends as pt  # noqa: E402
from core import well_package as wp  # noqa: E402
from core.repositories import mse_repository as mr  # noqa: E402
from tests.test_m133_mud_engineering import env  # noqa: E402,F401  (fixture: synthetic well with mud reports)

INVERTED_LOW_SHEAR = {"t3": {"value": 9.0, "class": me.ASSUMED}, "t6": {"value": 2.0, "class": me.ASSUMED}}


# ---- D54: package verification stays inside the package folder ----------------------------------------------
def _package(tmp_path, parts):
    folder = tmp_path / "pkg"
    folder.mkdir()
    (folder / wp.MANIFEST).write_text(json.dumps({"parts": parts}), encoding="utf-8")
    return str(folder)


def test_verify_refuses_entries_outside_the_folder_and_never_reads_them(tmp_path, monkeypatch):
    outside = tmp_path / "outside.html"
    outside.write_text("<html>not in the package</html>", encoding="utf-8")
    digest = wp.file_sha256(str(outside))
    folder = _package(tmp_path, [{"file": str(outside), "sha256": digest},
                                 {"file": "../outside.html", "sha256": digest},
                                 {"file": "sub/../../outside.html", "sha256": digest}])
    hashed = []
    real = wp.file_sha256
    monkeypatch.setattr(wp, "file_sha256", lambda path: hashed.append(os.path.abspath(path)) or real(path))
    result = wp.verify_package(folder)
    assert not result.ok and result.checked == 0
    assert sum(p.startswith("refused: manifest entry") for p in result.problems) == 3
    assert str(outside.resolve()) not in hashed                 # only the manifest itself was hashed
    assert hashed == [os.path.abspath(os.path.join(folder, wp.MANIFEST))]


@pytest.mark.parametrize("parts", [["eowr.html"], {"eowr.html": "ab"}, None, 7, [{"file": "a"}, "b"]])
def test_malformed_manifest_is_unreadable_not_an_exception(tmp_path, parts):
    result = wp.verify_package(_package(tmp_path, parts))
    assert not result.ok and result.problems and "unreadable" in result.problems[0]
    assert result.audit == "not checked"


def test_entry_without_a_file_name_and_an_empty_manifest_are_not_verified(tmp_path):
    no_name = wp.verify_package(_package(tmp_path, [{"sha256": "ab" * 32}]))
    assert not no_name.ok and no_name.problems == ["refused: manifest entry None is not a file name inside the "
                                                   "package folder"]
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    (empty_dir / wp.MANIFEST).write_text(json.dumps({"parts": []}), encoding="utf-8")
    empty = wp.verify_package(str(empty_dir))
    assert not empty.ok and empty.problems == ["nothing verified: the manifest lists no file with a SHA-256"]


def test_a_genuine_listing_still_verifies(tmp_path):
    folder = tmp_path / "pkg"
    folder.mkdir()
    (folder / "eowr.html").write_text("<html>EOWR</html>", encoding="utf-8")
    parts = [{"file": "eowr.html", "sha256": wp.file_sha256(str(folder / "eowr.html"))},
             {"file": "bit_runs.csv", "sha256": ""}]                      # an EMPTY part has no file
    (folder / wp.MANIFEST).write_text(json.dumps({"parts": parts}), encoding="utf-8")
    result = wp.verify_package(str(folder))
    assert (result.ok, result.problems, result.checked) == (True, [], 1)


# ---- D55: LSRYP from an inverted θ3 / θ6 pair (method version v2; v1 is replayed, never re-based) --------------
def test_inverted_low_shear_readings_give_no_lsryp_in_v2():
    sample = {"values": {"mw": 75.0, "pv": 20.0, "yp": 10.0}, "mud_report_id": 1, "report_date": "2026-04-01"}
    ev = me.evaluate(sample, INVERTED_LOW_SHEAR)
    row = ev.row("lsryp")
    assert (row.value, row.cls) == (None, me.UNKNOWN) and row.source.startswith("NOT ASSESSED: θ3 is above θ6")
    assert any(note.startswith("LSRYP NOT ASSESSED: θ3 (9) is above θ6 (2)") for note in ev.notes)
    assert me.evaluate(sample, INVERTED_LOW_SHEAR, version=me.MUD_VERSION_V1).row("lsryp").value == 16.0
    falling = {"t3": {"value": 5.0, "class": me.ASSUMED}, "t6": {"value": 7.0, "class": me.ASSUMED}}
    assert me.evaluate(sample, falling).row("lsryp").value == 3.0          # the M133 golden is unchanged
    with pytest.raises(me.MudEvaluationError, match="not available"):
        me.evaluate(sample, falling, version="M133 mud evaluation v0")


def test_a_stored_v1_case_is_repeated_and_re_run_as_v1(env):  # noqa: F811
    sample = me.load_sample(env["manager"], env["m1"])
    clean, problems = me.clean_readings(INVERTED_LOW_SHEAR)
    assert problems == []
    inputs = me.frozen_inputs(sample, clean, well_id=env["well"], wellbore_id=env["bore"])
    v1 = me.evaluate(inputs["sample"], clean, version=me.MUD_VERSION_V1).results()
    assert v1["lsryp"]["value"] == 16.0
    stored = cc.save_case(env["manager"], calculator=me.MUD_CALCULATOR, name="v1 case", inputs=inputs, results=v1,
                          method=me.MUD_METHOD, method_version=me.MUD_VERSION_V1, well_id=env["well"],
                          wellbore_id=env["bore"], note=me.MUD_LABEL)
    entry = next(e for e in ch.load_history(env["manager"], well_id=env["well"]) if e.record_id == stored["id"])
    outcome = ch.recalculate_entry(entry, env["manager"])
    assert outcome["status"] == "MATCH" and outcome["replayed_version"] == me.MUD_VERSION_V1
    assert f"with its own method version ({me.MUD_VERSION_V1}" in outcome["detail"]
    rerun = ch.save_recalculation(env["manager"], entry, outcome)
    assert rerun["method_version"] == me.MUD_VERSION_V1 and rerun["results"]["lsryp"]["value"] == 16.0
    fresh = me.save_evaluation(env["manager"], sample, INVERTED_LOW_SHEAR, well_id=env["well"],
                               wellbore_id=env["bore"])
    assert fresh["method_version"] == me.MUD_VERSION and fresh["results"]["lsryp"]["value"] is None


# ---- D56: service contracts accept values the UI cannot produce ---------------------------------------------
FIGURES = {"bit_no": "1", "rerun": 0, "footage_m": 100.0, "hours_on_bottom": 10.0}


@pytest.mark.parametrize("currency", ["USD\n", "usd", " USD", "US$", "", None, 840])
def test_currency_must_be_exactly_three_capital_letters(currency):
    out = br.cost_per_length(FIGURES, currency=currency, bit_cost=1000.0, rig_rate_per_day=24000.0, trip_hours=5.0)
    assert out.status == br.NOT_ASSESSED and out.cost_per_m is None
    assert any(reason.startswith("currency not entered") for reason in out.reasons)


def test_valid_currency_keeps_the_hand_golden():
    out = br.cost_per_length(FIGURES, currency="NOK", bit_cost=1000.0, rig_rate_per_day=24000.0, trip_hours=5.0)
    assert (out.status, out.currency) == (br.ASSESSED, "NOK")
    assert out.total_cost == pytest.approx(16000.0) and out.cost_per_m == pytest.approx(160.0)


@pytest.mark.parametrize("value", [True, False, math.nan, math.inf, -5.0, 0.0, "deep"])
def test_measured_depth_refuses_booleans_and_unusable_numbers(value):
    with pytest.raises(ValueError, match="Measured depth must be"):
        mr.md_in_metres(value, "m")
    assert mr.md_in_metres(100.0, "ft") == pytest.approx(30.48)


@pytest.mark.parametrize("text", ["25:00", "10:75", "-1:30", "24:00", "7", "ab:cd", None])
def test_npt_times_outside_a_day_have_no_interval(text):
    assert npt._minutes(text) is None
    assert npt._interval(text, "12:00") is None


def test_npt_valid_times_and_midnight_crossing_are_unchanged():
    assert npt._minutes("00:00") == 0 and npt._minutes("23:59") == 1439
    assert npt._interval("23:00", "01:00") == (1380, 1500)


class _Row:
    """A drilling-parameter row: every unset attribute is unrecorded (None)."""

    def __init__(self, **values):
        self.__dict__.update(values)

    def __getattr__(self, _name):
        return None


def test_trend_depth_axis_tells_invalid_from_unrecorded_depth():
    rows = [_Row(id=1, report_date=date(2026, 4, 1), depth_out=-50.0, avg_rop=12.0),
            _Row(id=2, report_date=date(2026, 4, 2), depth_out=None, avg_rop=14.0),
            _Row(id=3, report_date=date(2026, 4, 3), depth_out=1200.0, avg_rop=16.0)]
    rop = pt.build(rows, pt.AXIS_DEPTH).series["rop"]
    assert [p.x for p in rop.points] == [1200.0]
    assert [r for _d, _s, r in rop.not_placed] == ["depth out invalid (negative or non-numeric)",
                                                    "depth out not recorded"]
    assert [p.x for p in pt.build(rows, pt.AXIS_TIME).series["rop"].points] == [date(2026, 4, d) for d in (1, 2, 3)]
