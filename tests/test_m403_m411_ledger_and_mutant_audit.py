"""M403 traceability ledger (generated, never invents a directive) and M411 mutant-audit helpers."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "quality"))

import mutant_audit_m411 as audit  # noqa: E402
import traceability_ledger_m403 as ledger  # noqa: E402

STRICT = {state for _needle, state in ledger.STATES} | {ledger.TESTS_ONLY, ledger.GAP}


def test_the_committed_ledger_is_current_and_covers_m1_to_m400():
    assert ledger.main(["--check"]) == 0
    text = ledger.OUT.read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if re.match(r"\| M\d+ \|", line)]
    assert [int(r.split("|")[1].strip()[1:]) for r in rows] == list(range(1, 401))
    assert all("| UNAVAILABLE IN REPOSITORY |" in r for r in rows)
    assert all(r.split("|")[6].strip() in STRICT for r in rows)
    totals = [line for line in text.split("## Totals", 1)[1].splitlines() if line.startswith("| ") and "Missions" not in line]
    assert sum(int(line.split("|")[2]) for line in totals) == 400


def test_state_takes_the_most_limiting_label():
    assert ledger.state_of(["x IMPLEMENTED — PARTIALLY QUALIFIED", "y BLOCKED BY OWNER DECISION (P10)"]) == \
        "BLOCKED BY OWNER DECISION"
    assert ledger.state_of(["no label here"]) is None


def test_the_audit_names_the_innermost_enclosing_symbol():
    source = "X = 1\n\n\nclass A:\n    def run(self):\n        return 2 * X\n\n\ndef top():\n    return 3\n"
    assert audit.enclosing_symbol(source, "return 2 * X") == "run (l.6)"
    assert audit.enclosing_symbol(source, "return 3") == "top (l.10)"
    assert audit.enclosing_symbol(source, "X = 1") == "<module> (l.1)"
