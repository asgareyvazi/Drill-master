"""M79: the specialist method registry enforces the six-criteria rule."""
from __future__ import annotations

from pathlib import Path

from core import specialist_methods as sm

ROOT = Path(__file__).resolve().parents[1]


def test_registry_has_no_contradictions_and_every_blocker_is_recorded():
    assert sm.violations() == []
    for method in sm.METHODS:
        assert set(method.criteria) == set(sm.CRITERIA)
        assert method.implementable == (not method.unmet)
        if method.module:
            assert (ROOT / method.module).is_file()


def test_owner_gated_methods_stay_owner_review_and_nothing_new_is_implemented_with_gaps():
    assert sm.get("wellpath.iscwsa_error_model").status == "OWNER REVIEW REQUIRED"
    assert "licence" in sm.get("thermal.wellbore_temperature").unmet
    implemented = [m for m in sm.METHODS if m.status == "IMPLEMENTED"]
    assert all(m.implementable or "SCREENING" in m.limits for m in implemented)   # only the legacy SCREENING engine


def test_a_contradictory_entry_is_reported(monkeypatch):
    bad = sm.SpecialistMethod("x.y", "SYN", "s", "r", "own code", "a", (("a", "m"),), "limits", "none",
                              {c: c != "benchmark" for c in sm.CRITERIA}, "IMPLEMENTED", module="core/x.py")
    monkeypatch.setattr(sm, "METHODS", sm.METHODS + (bad,))
    problems = sm.violations()
    assert any("x.y: implemented with unmet criteria ['benchmark']" in p for p in problems)
    assert any("x.y: unmet criteria without a recorded blocker" in p for p in problems)
