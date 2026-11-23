"""M352 (A-9, R6): pre-push guard — large-font layout ratchet and repo-wide guard list (offscreen, SYNTHETIC)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "quality"))
import prepush_guard_m352 as guard  # noqa: E402

PROBE_ENV = dict(os.environ, QT_QPA_PLATFORM="offscreen", DRILLMASTER_ENV="test",
                 PYTHONPATH=os.pathsep.join([str(ROOT), str(ROOT / "tests")]))


def test_check_flags_widening_the_windows_limit_and_a_missing_budget():
    budget = {"knowledge_assistant": {"budget_px": 1200}, "calculation_history": {"budget_px": 2076}}
    assert guard.check({"knowledge_assistant": 1200, "calculation_history": 2000}, budget) == []
    problems = guard.check({"knowledge_assistant": 1301, "calculation_history": 2077}, budget)
    assert any("knowledge_assistant: minimum width 1301" in p and "exceeds its budget 1200" in p for p in problems)
    assert any("reaches the Windows limit 1300" in p for p in problems)
    assert any(p.startswith("calculation_history: minimum width 2077") for p in problems)
    assert guard.check({"well_architecture_panel": 900}, budget) == [
        "well_architecture_panel: no recorded budget (run --write and review the diff)"]


def test_changed_sources_select_their_panels_only():
    assert guard.panels_for(["tabs/knowledge_assistant.py", "core/report_sections.py"]) == ["knowledge_assistant"]
    assert guard.panels_for(["tabs/w3b_wellbore_schematic_tab.py"]) == ["well_architecture_panel"]
    assert guard.panels_for(["README.md"]) == []
    assert all((ROOT / t).exists() for t in guard.GUARD_TESTS)
    assert "tests/test_model_registry.py" in guard.GUARD_TESTS           # the d57f5b2 registry() class


def test_every_registered_panel_is_within_its_budget():
    proc = subprocess.run([sys.executable, str(ROOT / "tools/quality/prepush_guard_m352.py"), "--check"],
                          cwd=ROOT, env=PROBE_ENV, capture_output=True, text=True, timeout=600)
    if "NOT COMPARABLE" in proc.stdout:
        pytest.skip("font metrics differ from the recorded budgets: " + proc.stdout.strip())  # stated, never passed
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "M352 large-font probe (1.8× font)" in proc.stdout


WIDEN = r"""
import sys
sys.path.insert(0, "tools/quality")
import prepush_guard_m352 as guard
same, why = guard.comparable()
if not same:
    print("NOT COMPARABLE", why); raise SystemExit(0)
from PySide6.QtWidgets import QPushButton
import tabs.knowledge_assistant as kat
original = kat.KnowledgeAssistantPanel.__init__
def widened(self, *a, **k):
    # The original M320-E placement: both citation buttons in the evidence HEADER row (failed on Windows CI).
    original(self, *a, **k)
    outer = self.open_source_button.parentWidget().layout()
    rows = [outer.itemAt(i).layout() for i in range(outer.count()) if outer.itemAt(i).layout() is not None]
    header = next(r for r in rows if any(r.itemAt(j).widget() is self.open_source_button for j in range(r.count())))
    header.addWidget(QPushButton("Export with citations…"))
    header.addWidget(QPushButton("Verify citation file…"))
kat.KnowledgeAssistantPanel.__init__ = widened
problems = guard.check(guard.measure(["knowledge_assistant"]), guard.load_budget())
print("\n".join(problems) or "NO PROBLEM")
"""


def test_a_widened_row_is_caught_on_linux_fonts():
    """The A-9 regression itself: the M320-E buttons in the header row push the panel past its budget and limit."""
    proc = subprocess.run([sys.executable, "-c", WIDEN], cwd=ROOT, env=PROBE_ENV, capture_output=True, text=True,
                          timeout=600)
    if proc.stdout.startswith("NOT COMPARABLE"):
        pytest.skip(proc.stdout.strip())
    assert "exceeds its budget" in proc.stdout and "Windows limit 1300" in proc.stdout, proc.stdout + proc.stderr


def test_the_hook_runs_the_changed_mode():
    hook = (ROOT / "tools/hooks/pre-push").read_text(encoding="utf-8")
    assert "prepush_guard_m352.py --changed" in hook and os.access(ROOT / "tools/hooks/pre-push", os.X_OK)
