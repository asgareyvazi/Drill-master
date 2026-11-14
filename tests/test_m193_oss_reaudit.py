"""M193: the 50-repository register re-audit is parsed and judged deterministically (offline)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _tool():
    spec = importlib.util.spec_from_file_location("oss_reaudit_m193", ROOT / "tools" / "quality" / "oss_reaudit_m193.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_register_holds_fifty_repositories_with_sha_licence_and_classification():
    tool = _tool()
    entries = tool.parse_register(tool.REGISTER.read_text(encoding="utf-8"))
    assert [e["number"] for e in entries] == list(range(1, 51))
    assert all(len(e["sha"]) == 40 and e["licence"] and e["classification"] for e in entries)
    welleng = next(e for e in entries if e["repository"] == "jonnymaserati/welleng")
    assert welleng["sha"].startswith("d29adf906b") and welleng["licence"] == "Apache-2.0"
    assert welleng["classification"] == "REUSE ALGORITHM"


def test_assessment_never_upgrades_a_classification_and_flags_licence_changes():
    tool = _tool()
    entry = {"number": 1, "repository": "o/r", "sha": "a" * 40, "licence": "none detected",
             "classification": "INSPIRE ONLY"}
    same = tool.assess(entry, {"sha": "a" * 40, "spdx": None, "archived": False})
    assert same["state"] == tool.UNCHANGED and same["classification"] == "INSPIRE ONLY"
    assert tool.assess(entry, {"sha": "a" * 40, "spdx": "NOASSERTION"})["state"] == tool.UNCHANGED
    gained = tool.assess(entry, {"sha": "b" * 40, "spdx": "MIT", "archived": True})
    assert gained["state"] == "; ".join([tool.LICENCE_CHANGED, tool.ARCHIVED, tool.MOVED])
    assert gained["classification"] == "INSPIRE ONLY"                  # a person re-reviews; nothing is adopted
    mit = dict(entry, licence="MIT")
    assert tool.assess(mit, {"sha": "a" * 40, "spdx": "Apache-2.0"})["state"] == tool.LICENCE_CHANGED
    assert tool.assess(mit, None)["state"] == tool.GONE
    assert tool.assess(mit, None, error="boom")["state"] == tool.ERROR


def test_a_failed_lookup_is_not_checked_never_unchanged():
    tool = _tool()
    entries = [{"number": 1, "repository": "o/r", "sha": "a" * 40, "licence": "MIT", "classification": "REJECT"}]

    def broken(_repository):
        raise RuntimeError("network down")

    result = tool.reaudit(entries, broken)
    assert result[0]["state"] == tool.ERROR and "network down" in result[0]["detail"]
    assert tool.summary(result) == {tool.ERROR: 1}


def test_the_committed_evidence_covers_all_fifty_repositories():
    evidence = json.loads((ROOT / "docs" / "mission-reports" / "m171-m200-evidence" / "oss_reaudit_m193.json")
                          .read_text(encoding="utf-8"))
    assert evidence["contract"] == "oss-reaudit-m193-v1" and len(evidence["results"]) == 50
    assert sum(evidence["summary"].values()) >= 50 and "NOT CHECKED" not in evidence["summary"]
