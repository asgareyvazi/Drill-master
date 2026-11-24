"""M386: the known-vulnerability audit of the runtime lock (offline: the PyPI lookup is replaced by a stub)."""
from __future__ import annotations

import sys
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "quality"))

import vuln_audit_m386 as va  # noqa: E402

LOCK = "# comment\nalpha==1.0\nbeta==2.0 ; python_version>='3.11'\n\ngamma==3.0\nnot a pin\n"


def _fetch(table):
    def fetch(name, version):
        value = table[name]
        if isinstance(value, Exception):
            raise value
        return value
    return fetch


def test_lock_pins_are_parsed_exactly():
    assert va.parse_lock(LOCK) == [{"name": "alpha", "version": "1.0"}, {"name": "beta", "version": "2.0"},
                                   {"name": "gamma", "version": "3.0"}]


def test_states_and_exit_codes():
    advisory = {"id": "GHSA-x", "fixed_in": ["2.1"], "summary": "s", "withdrawn": None}
    withdrawn = dict(advisory, id="GHSA-old", withdrawn="2026-01-01")
    rows = va.audit(va.parse_lock(LOCK), _fetch({"alpha": {"vulnerabilities": []},
                                                  "beta": {"vulnerabilities": [advisory, withdrawn]},
                                                  "gamma": {"vulnerabilities": [withdrawn]}}))
    assert [r["state"] for r in rows] == [va.CLEAN, va.VULNERABLE, va.CLEAN]
    assert rows[1]["reason"] == "1 advisory(ies)" and rows[1]["advisories"][0]["fixed_in"] == ["2.1"]
    assert va.exit_code(rows) == 1
    assert va.exit_code([rows[0], rows[2]]) == 0


def test_a_failed_lookup_is_not_checked_never_clean():
    rows = va.audit(va.parse_lock(LOCK), _fetch({"alpha": urllib.error.URLError("offline"),
                                                  "beta": {"info": {}}, "gamma": {"vulnerabilities": []}}))
    assert [r["state"] for r in rows] == [va.NOT_CHECKED, va.NOT_CHECKED, va.CLEAN]
    assert va.exit_code(rows) == 2 and va.exit_code([]) == 2
    assert va.summary(rows) == {va.NOT_CHECKED: 2, va.CLEAN: 1}


def test_the_committed_evidence_matches_the_lock():
    import json

    evidence = json.loads((ROOT / "docs" / "mission-reports" / "m361-m400-evidence" /
                           "m386_vuln_audit_after.json").read_text(encoding="utf-8"))
    pins = va.parse_lock((ROOT / "requirements-lock.txt").read_text(encoding="utf-8"))
    assert [(r["name"], r["version"]) for r in evidence["rows"]] == [(p["name"], p["version"]) for p in pins]
    assert evidence["summary"] == {va.CLEAN: len(pins)}
