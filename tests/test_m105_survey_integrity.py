"""M105: survey derived-result integrity (every field), results hash, fail-closed engineering use.

Tampering is simulated out of band (the immutability trigger is dropped on the raw file, exactly
as an external edit would bypass the application); the application must detect it on read and
refuse to use the revision.  Synthetic stations only.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import storage_guards  # noqa: E402
from core import survey_revisions as sr  # noqa: E402
from tests.test_m70_integrity import _open, _seed  # noqa: E402

ROWS = [{"md": 0.0, "inc": 0.0, "azi": 0.0}, {"md": 300.0, "inc": 0.0, "azi": 0.0},
        {"md": 600.0, "inc": 20.0, "azi": 357.0}, {"md": 900.0, "inc": 35.0, "azi": 10.0}]


@pytest.fixture
def env(tmp_path, monkeypatch):
    path = tmp_path / "m105.sqlite"
    manager = _open(path, tmp_path, monkeypatch)
    ids = _seed(manager)
    yield manager, path, ids
    manager.close()


def _save(manager, ids):
    return sr.save_revision(manager, ids["A"][0], ROWS, depth_datum="RKB", azimuth_reference="true")


def _tamper(manager, path, revision_id, *, results=None, clear_results_hash=False):
    manager.close()
    with sqlite3.connect(path) as con:
        for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='trigger' "
                                   "AND name LIKE 'trg_survey_revision_immutable%'").fetchall():
            con.execute(f"DROP TRIGGER {name}")
        if results is not None:
            con.execute("UPDATE survey_revisions SET results_json=? WHERE id=?", (json.dumps(results), revision_id))
        if clear_results_hash:
            con.execute("UPDATE survey_revisions SET results_sha256=NULL WHERE id=?", (revision_id,))
    manager.initialize()
    return sr.get_revision(manager, revision_id)


def test_a_new_revision_records_and_verifies_its_results_hash_and_every_field(env):
    manager, _path, ids = env
    rev = _save(manager, ids)
    assert rev["results_integrity"] == "VERIFIED" and len(rev["results_sha256"]) == 64
    check = sr.verify_results(rev)
    assert check["status"] == "MATCH" and check["issue_count"] == 0
    assert check["fields_checked"] == ["md", "inc", "azi", "tvd", "north", "east", "vs", "hd", "dls"]
    assert check["tolerances"]["dls"] == {"unit": "deg/30m", "tolerance": 1e-6}
    assert check["tolerances"]["azi"]["unit"] == "deg"
    assert sr.verify_for_use(rev, "test")["status"] == "MATCH"


@pytest.mark.parametrize("field", ["md", "inc", "azi", "tvd", "north", "east", "vs", "hd", "dls"])
def test_altering_any_single_result_field_is_detected(env, field):
    manager, _path, ids = env
    rev = _save(manager, ids)
    altered = dict(rev)
    altered["results"] = [dict(r) for r in rev["results"]]
    altered["results"][2][field] = float(altered["results"][2][field]) + 0.01
    check = sr.verify_results(altered)
    assert check["status"] == "DIFFERENT", field
    assert any(f": {field} differs" in issue for issue in check["issues"]), check["issues"]
    with pytest.raises(sr.SurveyRevisionError, match="do not match its stations"):
        sr.verify_for_use(altered, "a plan tie-in")


@pytest.mark.parametrize("field", list(sr.RESULT_FIELDS))
def test_each_field_is_held_to_its_own_tolerance(env, field):
    manager, _path, ids = env
    rev = _save(manager, ids)
    tol = sr.RESULT_FIELDS[field][1]
    for factor, expected in ((0.1, "MATCH"), (10.0, "DIFFERENT")):
        altered = dict(rev, results=[dict(r) for r in rev["results"]])
        altered["results"][3][field] = float(altered["results"][3][field]) + factor * tol
        assert sr.verify_results(altered)["status"] == expected, (field, factor)


def test_azimuth_compares_across_the_360_wrap(env):
    manager, _path, ids = env
    rev = _save(manager, ids)
    assert rev["results"][0]["azi"] == pytest.approx(0.0)
    near = dict(rev, results=[dict(r) for r in rev["results"]])
    near["results"][0]["azi"] = 360.0 - 1e-9          # the same direction
    assert sr.verify_results(near)["status"] == "MATCH"
    far = dict(rev, results=[dict(r) for r in rev["results"]])
    far["results"][0]["azi"] = 359.9                    # 0.1 deg off
    assert sr.verify_results(far)["status"] == "DIFFERENT"


def test_missing_extra_reordered_truncated_and_non_finite_results_are_detected(env):
    manager, _path, ids = env
    rev = _save(manager, ids)
    base = [dict(r) for r in rev["results"]]

    def check(results):
        return sr.verify_results(dict(rev, results=results))

    missing = [dict(r) for r in base]
    del missing[1]["dls"]
    out = check(missing)
    assert out["status"] == "DIFFERENT" and any("missing ['dls']" in i for i in out["issues"])
    extra = [dict(r) for r in base]
    extra[1]["sf"] = 3.0
    out = check(extra)
    assert out["status"] == "DIFFERENT" and any("extra ['sf']" in i for i in out["issues"])
    assert check(list(reversed(base)))["status"] == "DIFFERENT"
    truncated = check(base[:-1])
    assert truncated["status"] == "DIFFERENT" and "3 stored vs 4 recomputed" in truncated["detail"]
    nan = [dict(r) for r in base]
    nan[3]["tvd"] = math.nan
    out = check(nan)
    assert out["status"] == "DIFFERENT" and any("not a finite number" in i for i in out["issues"])
    nulled = [dict(r) for r in base]
    nulled[3]["east"] = None
    assert check(nulled)["status"] == "DIFFERENT"
    assert check("not a list")["status"] == "DIFFERENT"


def test_tampered_results_with_a_recorded_hash_are_refused_everywhere(env):
    manager, path, ids = env
    rev = _save(manager, ids)
    child = sr.save_revision(manager, ids["A"][0], ROWS + [{"md": 1200.0, "inc": 40.0, "azi": 12.0}],
                             mode="replace", parent_id=rev["id"], depth_datum="RKB", azimuth_reference="true")
    results = [dict(r) for r in rev["results"]]
    results[-1]["tvd"] += 5.0
    bad = _tamper(manager, path, rev["id"], results=results)
    assert bad["integrity"] == "VERIFIED"               # stations untouched: the station hash alone passes
    assert bad["results_integrity"] == "HASH MISMATCH"
    with pytest.raises(sr.SurveyRevisionError, match="SHA-256 check"):
        sr.tie_in_from_revision(bad)
    with pytest.raises(sr.SurveyRevisionError, match="SHA-256 check"):
        sr.transform_revision(manager, bad["id"], "grid", convergence_deg=1.0, parameter_source="test")
    diff = sr.compare_revisions(bad, sr.get_revision(manager, child["id"]))
    assert diff["comparable"] is False and "SHA-256" in diff["reason"]


def test_a_pre_m105_revision_without_results_hash_is_not_recorded_but_still_fully_verified(env):
    manager, path, ids = env
    rev = _save(manager, ids)
    legacy = _tamper(manager, path, rev["id"], clear_results_hash=True)
    assert legacy["results_sha256"] is None and legacy["results_integrity"] == "NOT RECORDED"
    tie = sr.tie_in_from_revision(legacy)                # honest legacy data is still usable
    assert tie["tvd"] == pytest.approx(legacy["results"][-1]["tvd"])
    # ... but tampered legacy results (no hash to catch them) are refused by the full recomputation
    results = [dict(r) for r in legacy["results"]]
    results[-1]["north"] += 2.0
    forged = _tamper(manager, path, rev["id"], results=results)
    assert forged["integrity"] == "VERIFIED" and forged["results_integrity"] == "NOT RECORDED"
    with pytest.raises(sr.SurveyRevisionError, match="north differs"):
        sr.tie_in_from_revision(forged)


def test_a_revision_without_an_integrity_state_is_not_treated_as_verified(env):
    manager, _path, ids = env
    rev = _save(manager, ids)
    stripped = {k: v for k, v in rev.items() if k != "integrity"}
    with pytest.raises(sr.SurveyRevisionError, match="station hash"):
        sr.tie_in_from_revision(stripped)


def test_an_old_database_gains_the_results_hash_column_without_backfill(env):
    manager, path, ids = env
    rev = _save(manager, ids)
    manager.close()
    with sqlite3.connect(path) as con:                   # the pre-M105 schema had no such column
        # ... and its survey guard was v1, which did not name the column (M116 D32: v2 freezes it)
        for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='trigger' "
                                   "AND name LIKE 'trg_survey_revision_immutable%'").fetchall():
            con.execute(f"DROP TRIGGER {name}")
        legacy = [c for c in storage_guards._SURVEY_FROZEN if c != "results_sha256"]
        con.execute("CREATE TRIGGER trg_survey_revision_immutable_v1 BEFORE UPDATE ON survey_revisions WHEN "
                    + " OR ".join(f"NEW.{c} IS NOT OLD.{c}" for c in legacy) + " BEGIN SELECT RAISE(ABORT, "
                    "'survey_revisions: a saved survey revision is immutable'); END")
        con.execute("ALTER TABLE survey_revisions DROP COLUMN results_sha256")
        assert "results_sha256" not in {r[1] for r in con.execute("PRAGMA table_info(survey_revisions)")}
    manager.initialize()                                 # additive migration on startup
    with sqlite3.connect(path) as con:
        assert "results_sha256" in {r[1] for r in con.execute("PRAGMA table_info(survey_revisions)")}
        names = storage_guards.installed(con)               # column first, then the v2 guard that freezes it
        assert "trg_survey_revision_immutable_v2" in names and "trg_survey_revision_immutable_v1" not in names
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            con.execute("UPDATE survey_revisions SET results_sha256='0' WHERE id=?", (rev["id"],))
    old = sr.get_revision(manager, rev["id"])
    assert old["results_sha256"] is None and old["results_integrity"] == "NOT RECORDED"
    manager.initialize()                                 # idempotent
    assert sr.get_revision(manager, rev["id"])["results_integrity"] == "NOT RECORDED"
