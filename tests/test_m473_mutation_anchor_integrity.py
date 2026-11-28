"""M473-M474 (U3): the M261-M290 mutation-only phases (M275 TR, M276 AC, M278 MV, M279 CP, M282 BP, M283 WC) and
the M461-M520 mutants stay runnable: every anchor matches its file exactly once (an INVALID mutant is never a kill).

This is a static check (no mutant is executed here); the executed results are in
``docs/mission-reports/m461-m520-evidence/m473_u3_historical_mutation_rerun.json`` and ``m468_mutation_eowr.json``.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
U3_FAMILIES = {"TR": 4, "AC": 12, "MV": 4, "CP": 5, "BP": 7, "WC": 7}     # counts from the M261-M290 report


def _load(name):
    import sys
    sys.path.insert(0, str(ROOT / "tools" / "quality"))
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / "quality" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _anchor_counts(mutants):
    return {m.id: (ROOT / m.path).read_text(encoding="utf-8").count(m.old) for m in mutants}


def test_u3_families_have_the_reported_counts_and_valid_anchors():
    mutants = [m for m in _load("mutation_m261_m290").MUTANTS if m.id.split("-")[0] in U3_FAMILIES]
    counts = {f: sum(1 for m in mutants if m.id.startswith(f + "-")) for f in U3_FAMILIES}
    assert counts == U3_FAMILIES
    assert {k: v for k, v in _anchor_counts(mutants).items() if v != 1} == {}
    assert all(m.tests and all((ROOT / t).exists() for t in m.tests) for m in mutants)


@pytest.mark.parametrize("tool", ["mutation_m461_m520", "mutation_m321_m360", "mutation_m361_m400", "mutation_m401_m460",
                                  "mutation_m261_m290"])     # M494 R4b: all 89 M261-M290 anchors valid again
def test_current_mutation_tools_have_valid_anchors(tool):
    mutants = _load(tool).MUTANTS
    assert len({m.id for m in mutants}) == len(mutants)
    assert {k: v for k, v in _anchor_counts(mutants).items() if v != 1} == {}
