"""M352 (A-9, roadmap R6): fast pre-push guard — large-font layout ratchet plus the repo-wide AST guards.

Why: offscreen Linux fonts are narrower than Windows Segoe UI, so a widened panel passed locally and failed only on
the Windows CI job (M320 E, knowledge panel > 1300 px). And repo-wide AST guards ran only in the full suite (the
``registry()`` regression in d57f5b2). This guard catches both classes before a push, in about a minute.

Large-font ratchet: each registered panel is built with the application font scaled by ``SCALE`` (1.8) and its
``minimumSizeHint().width()`` must not exceed its recorded budget (``docs/engineering/large_font_budget_m352.json``);
a panel with a hard Windows limit (``absolute_px``) must also stay below it. Budgets change only with ``--write``
(reviewed in the diff, never raised silently). Linux font metrics are NOT Windows metrics: the ratchet detects
widening, it does not prove the Windows width.

    python tools/quality/prepush_guard_m352.py --check            # every panel (CI test uses this)
    python tools/quality/prepush_guard_m352.py --changed          # only panels whose sources changed vs upstream
    python tools/quality/prepush_guard_m352.py --write            # record the current widths as budgets
    git config core.hooksPath tools/hooks                         # installs tools/hooks/pre-push
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
BUDGET = ROOT / "docs" / "engineering" / "large_font_budget_m352.json"
SCALE = 1.8
GUARD_VERSION = "M352 pre-push guard v1"
#: repo-wide AST / boundary guards that only the full suite used to run (roadmap R6)
GUARD_TESTS = ("tests/test_model_registry.py", "tests/test_release_boundary_imports.py",
               "tests/test_m112_dependency_audit.py")


def _schematic_architecture(db):
    from tabs.w3b_wellbore_schematic_tab import WellboreSchematicTab

    tab = WellboreSchematicTab(db)
    panel = tab.architecture_panel
    panel._probe_owner = tab                       # keep the owning tab alive while measured
    return panel


def _knowledge(db):
    from tabs.knowledge_assistant import KnowledgeAssistantPanel

    return KnowledgeAssistantPanel(db)


def _calculation_history(db):
    from tabs.calculation_history_tab import CalculationHistoryTab

    return CalculationHistoryTab(db)


#: panel id -> (factory, source files whose change triggers the probe, hard Windows limit in px or None)
PANELS: Dict[str, Tuple[Callable, Tuple[str, ...], Optional[int]]] = {
    "knowledge_assistant": (_knowledge, ("tabs/knowledge_assistant.py", "tabs/documents_tab.py"), 1300),
    "well_architecture_panel": (_schematic_architecture,
                                ("tabs/well_architecture_panel.py", "tabs/w3b_wellbore_schematic_tab.py"), None),
    "calculation_history": (_calculation_history, ("tabs/calculation_history_tab.py",), None),
}


REFERENCE_TEXT = "The quick brown fox jumps over the lazy dog 0123456789"


def font_fingerprint() -> str:
    """Family, size and the advance of a reference string at ``SCALE``: budgets compare only on the same metrics."""
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    font = type(QApplication.font())(QApplication.font())
    font.setPointSizeF((font.pointSizeF() if font.pointSizeF() > 0 else 9.0) * SCALE)
    return f"{font.family()}|{font.pointSizeF():g}pt|{QFontMetrics(font).horizontalAdvance(REFERENCE_TEXT)}px"


def measure(panel_ids: List[str]) -> Dict[str, int]:
    """Minimum widths (px) at ``SCALE`` × the application font, on a throw-away SYNTHETIC database."""
    from PySide6.QtWidgets import QApplication

    sys.path.insert(0, str(ROOT / "tests"))
    from synthetic_operations import build_synthetic_operations, make_file_database

    app = QApplication.instance() or QApplication([])
    original = QApplication.font()
    scaled = type(original)(original)
    scaled.setPointSizeF((original.pointSizeF() if original.pointSizeF() > 0 else 9.0) * SCALE)
    folder = tempfile.mkdtemp(prefix="m352_")
    db = make_file_database(Path(folder) / "probe.db")
    build_synthetic_operations(db)
    out: Dict[str, int] = {}
    app.setFont(scaled)
    try:
        for pid in panel_ids:
            widget = PANELS[pid][0](db)
            widget.show()                          # polish + activate: unshown size hints are stale (found in M352)
            app.processEvents()
            out[pid] = int(widget.minimumSizeHint().width())
            widget.hide()
            owner = getattr(widget, "_probe_owner", widget)
            if hasattr(widget, "cleanup"):
                widget.cleanup()
            owner.deleteLater()
            app.processEvents()
    finally:
        app.setFont(original)
        db.engine.dispose()
    return out


def load_budget_file() -> Dict[str, object]:
    return json.loads(BUDGET.read_text(encoding="utf-8")) if BUDGET.exists() else {}


def load_budget() -> Dict[str, Dict[str, object]]:
    return load_budget_file().get("panels", {})


def comparable() -> Tuple[bool, str]:
    """(True, fingerprint) when this machine's font metrics are the ones the budgets were recorded with."""
    here, recorded = font_fingerprint(), load_budget_file().get("font_fingerprint")
    return here == recorded, (f"font metrics here {here!r}" if here == recorded else
                              f"font metrics here {here!r} differ from the recorded {recorded!r}")


def check(widths: Dict[str, int], budget: Dict[str, Dict[str, object]]) -> List[str]:
    problems: List[str] = []
    for pid, width in widths.items():
        limit = PANELS[pid][2]
        entry = budget.get(pid)
        if entry is None:
            problems.append(f"{pid}: no recorded budget (run --write and review the diff)")
        elif width > int(entry["budget_px"]):
            problems.append(f"{pid}: minimum width {width} px at {SCALE}× font exceeds its budget "
                            f"{entry['budget_px']} px — a layout row was widened (Windows fonts are wider still)")
        if limit is not None and width >= limit:
            problems.append(f"{pid}: minimum width {width} px at {SCALE}× font reaches the Windows limit {limit} px")
    return problems


def changed_files(base: Optional[str] = None) -> List[str]:
    def git(*args) -> List[str]:
        proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
        return proc.stdout.split() if proc.returncode == 0 else []

    ref = base or (git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}") or ["HEAD~1"])[0]
    return sorted(set(git("diff", "--name-only", f"{ref}...HEAD") + git("diff", "--name-only")
                      + git("diff", "--name-only", "--cached")))


def panels_for(files: List[str]) -> List[str]:
    return [pid for pid, (_f, sources, _l) in PANELS.items() if any(f in sources for f in files)]


def run_guard_tests() -> int:
    env = dict(os.environ, QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    return subprocess.call([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *GUARD_TESTS],
                           cwd=ROOT, env=env)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="probe every registered panel")
    mode.add_argument("--changed", action="store_true", help="pre-push: AST guards + panels whose sources changed")
    mode.add_argument("--write", action="store_true", help="record the current widths as the budgets")
    parser.add_argument("--base", help="diff base for --changed (default: the upstream branch)")
    args = parser.parse_args(argv)
    if args.write:
        widths = measure(list(PANELS))
        BUDGET.write_text(json.dumps({"version": GUARD_VERSION, "scale": SCALE,
                                      "font_fingerprint": font_fingerprint(), "panels": {
            pid: {"budget_px": w, "absolute_px": PANELS[pid][2], "sources": list(PANELS[pid][1])}
            for pid, w in widths.items()}}, indent=2) + "\n", encoding="utf-8")
        print(f"budgets written: {widths}")
        return 0
    status = 0
    if args.changed:
        if run_guard_tests() != 0:
            print("M352: repo-wide guard tests failed", file=sys.stderr)
            status = 1
        targets = panels_for(changed_files(args.base))
    else:
        targets = list(PANELS)
    same, why = comparable()
    if targets and not same:
        print(f"M352 large-font probe: NOT COMPARABLE — {why}; the widths are not judged here (re-record on this "
              f"machine only with --write and a reviewed diff)")
        targets = []
        status = status or (2 if args.check and os.environ.get("M352_REQUIRE_COMPARABLE") else 0)
    elif targets:
        widths = measure(targets)
        problems = check(widths, load_budget())
        for line in problems:
            print(f"M352: {line}", file=sys.stderr)
        print(f"M352 large-font probe ({SCALE}× font): {widths}")
        status = status or (1 if problems else 0)
    elif same:
        print("M352 large-font probe: no registered panel changed")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
