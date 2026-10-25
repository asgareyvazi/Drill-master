#!/usr/bin/env python3
"""Repeatable mutation run for the M46 fixes and the contracts they touch.

Each mutant replaces ONE exact snippet (it must occur exactly once in the
file, otherwise the mutant is reported INVALID) in a scratch copy of the
working tree - the repository itself is never modified.  The listed tests
run against the mutated copy; a mutant is KILLED when they fail, SURVIVED
when they pass.  A baseline run of every listed test on the unmutated copy
must pass first.  Mutants that cannot change behaviour are declared with
``equivalent=<reason>`` and are still applied and run, so the claim is
checked (an "equivalent" mutant that is killed is reported as such).

Exit status 0 only when the baseline passes, no mutant is INVALID and every
non-equivalent mutant is KILLED.

Usage::

    python tools/quality/mutation_m46.py [--json OUT] [--only ID[,ID...]]

The environment must be able to run the tests (Qt offscreen etc., see
tools/qt_headless_env.sh).  SYNTHETIC test data only.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

SEARCH_TESTS = ["tests/test_search_parity_m46.py", "tests/test_search_normalization.py"]
LINK_TESTS = ["tests/test_document_links_audit_m46.py", "tests/test_document_links.py"]
VIEW3D_TESTS = ["tests/test_trajectory_3d_lifecycle_m46.py", "tests/test_trajectory_3d.py"]


@dataclass
class Mutant:
    id: str
    path: str
    old: str
    new: str
    tests: list
    note: str
    equivalent: str = ""
    result: dict = field(default_factory=dict)


MUTANTS = [
    # ---------------------------------------------------------------- T1 test isolation
    Mutant("T1-restore", "tests/conftest.py", "        permissions._user = previous\n", "        pass\n",
           ["tests/test_test_isolation_m46.py"], "principal no longer restored after a test"),
    Mutant("T1-snapshot", "tests/conftest.py", "    previous = permissions._user\n", "    previous = None\n",
           ["tests/test_test_isolation_m46.py"], "restores 'nobody' instead of the previous principal"),
    # ---------------------------------------------------------------- S1-S3 search v2
    Mutant("S-version", "core/search_normalization.py", "NORMALIZATION_VERSION = 2\n", "NORMALIZATION_VERSION = 1\n",
           SEARCH_TESTS, "index signature not bumped: v1 indexes would be reused"),
    Mutant("S-combining", "core/search_normalization.py",
           ",\n                      *(chr(c) for c in range(0x0300, 0x0370))])", "])",
           SEARCH_TESTS, "combining diacritics U+0300-036F kept"),
    Mutant("S-latin-fold", "core/search_normalization.py",
           "        return decomposed[0]\n    return None", "        return None\n    return None",
           SEARCH_TESTS, "Latin letters with diacritics not folded"),
    Mutant("S-latin-ascii-guard", "core/search_normalization.py",
           "decomposed[0].isascii() and decomposed[0].isalpha()", "decomposed[0].isalpha()",
           SEARCH_TESTS, "non-ASCII bases folded too (would merge alef forms if applied to Arabic ranges)",
           equivalent="the fold tables only cover U+00C0-024F and U+1E00-1EFF, whose canonical "
                      "decompositions all start with an ASCII letter or are not decomposable; "
                      "the guard documents intent and protects future range additions"),
    Mutant("S-token-underscore", "core/search_normalization.py",
           '_TOKEN = re.compile(r"[^\\W_]+", re.UNICODE)', '_TOKEN = re.compile(r"\\w+", re.UNICODE)',
           SEARCH_TESTS, "'_' part of a word again (v1)"),
    Mutant("S-alt-halfspace", "core/search_normalization.py",
           "            alternatives.append(groups[:i] + [[left[0] + right[0]]] + groups[i + 2:])\n",
           "            pass\n", SEARCH_TESTS, "no half-space alternative (fallback and FTS)"),
    Mutant("S-alt-ascii", "core/search_normalization.py",
           "and not left[0].isascii() and not right[0].isascii():", ":",
           SEARCH_TESTS, "English words also joined ('drill pipe' -> 'drillpipe')"),
    Mutant("S-phrase-any-order", "core/search_normalization.py",
           "    return any(page_tokens[i:i + n] == wanted for i in range(len(page_tokens) - n + 1))",
           "    return all(any(t.startswith(w) for t in page_tokens) for w in wanted)",
           SEARCH_TESTS, "fallback phrase = loose prefixes anywhere (v1 false positives)"),
    Mutant("S-single-exact", "core/search_normalization.py",
           "        return any(token.startswith(wanted[0]) for token in page_tokens)",
           "        return wanted[0] in page_tokens", SEARCH_TESTS, "fallback single word exact, not prefix"),
    Mutant("S-scan-v1", "core/document_library.py", "            if text_matches(text, groups):",
           "            if all(find_spans(text, [t]) for g in groups for t in g):",
           SEARCH_TESTS, "fallback scan back to per-term prefix spans (v1)"),
    # ---------------------------------------------------------------- W1 survey editor scope
    Mutant("W1-filter", "tabs/w6_Trajectory_Widget.py",
           "                points = [p for p in points if p.get('report_id') is None]\n", "                pass\n",
           ["tests/test_survey_editor_scope_m46.py"], "well scope lists every report's rows again"),
    Mutant("W1-condition", "tabs/w6_Trajectory_Widget.py", "            if not self.current_report_id:\n",
           "            if True:\n", ["tests/test_survey_editor_scope_m46.py"],
           "well-level filter also applied with a report selected"),
    # ---------------------------------------------------------------- H1 hierarchy worker connection
    Mutant("H1-shared-connection", "main_window.py",
           "                with worker_database(self.db_manager) as db:\n                    result = db.get_full_hierarchy()",
           "                result = self.db_manager.get_full_hierarchy()",
           ["tests/test_hierarchy_worker_isolation_m46.py"], "worker reads on the shared connection again"),
    # ---------------------------------------------------------------- links: atomicity and authorization
    Mutant("L-audit-swallowed", "core/document_links.py",
           '            raise DocumentLinkError("audit_failed", type(exc).__name__) from exc', "            return",
           LINK_TESTS, "audit failure ignored: link stored without audit"),
    Mutant("L-run-commit-classify", "core/document_links.py",
           '            logger.error("Document link operation rolled back: %s", type(exc).__name__)\n'
           '            raise DocumentLinkError("failed", type(exc).__name__) from exc',
           '            logger.error("Document link operation rolled back: %s", type(exc).__name__)\n'
           '            return None', LINK_TESTS, "unexpected failure reported as success"),
    Mutant("L-denied-classify", "core/document_links.py",
           '            raise DocumentLinkError("denied") from exc', '            raise DocumentLinkError("failed") from exc',
           LINK_TESTS, "authorization refusal not classified as denied"),
    Mutant("L-duplicate-classify", "core/document_links.py",
           '                raise DocumentLinkError("duplicate") from exc',
           '                raise DocumentLinkError("failed", "IntegrityError") from exc',
           LINK_TESTS, "lost race against the unique constraint not reported as duplicate"),
    Mutant("L-report-well", "core/document_links.py", "            if report.well_id != well.id:\n",
           "            if False:\n", LINK_TESTS, "report of another well accepted"),
    Mutant("L-page", "core/document_links.py",
           '            raise DocumentLinkError("page_missing")', "            pass",
           LINK_TESTS, "anchor page that does not exist accepted"),
    Mutant("L-change-audit", "core/document_links.py",
           '            self._audit(session, "document_link_change", document,',
           '            (lambda *a: None)(session, "document_link_change", document,',
           LINK_TESTS, "change not audited"),
    Mutant("L-remove-audit", "core/document_links.py",
           '            self._audit(session, "document_unlink", document, {"link_id": link_id, **before})',
           "            pass", LINK_TESTS, "removal not audited"),
    # ---------------------------------------------------------------- 3D draw timer lifecycle
    Mutant("V-hidden-draw", "tabs/trajectory_3d_view.py",
           "        if not self.canvas.isVisible():                  # drawn by showEvent instead\n            return\n",
           "", VIEW3D_TESTS, "draws while hidden"),
    Mutant("V-dirty-reset", "tabs/trajectory_3d_view.py",
           "        self._dirty = False\n        self.canvas.draw()", "        self.canvas.draw()",
           VIEW3D_TESTS, "request flag never cleared"),
    Mutant("V-show-rearm", "tabs/trajectory_3d_view.py",
           "        if self._dirty:\n            self._draw_timer.start()", "        pass",
           VIEW3D_TESTS, "a request made while hidden is dropped on show"),
    Mutant("V-coalesce", "tabs/trajectory_3d_view.py",
           "            self._dirty = True\n            self._draw_timer.start()",
           "            self._dirty = True\n            self.canvas.draw()", VIEW3D_TESTS,
           "every request draws immediately (no coalescing)"),
    Mutant("V-draw-idle-route", "tabs/trajectory_3d_view.py",
           "            self.canvas.draw_idle = self._request_draw   # every redraw request uses the owned timer\n",
           "", VIEW3D_TESTS, "Matplotlib's draw_idle not routed to the owned timer"),
    Mutant("V-timer-owner", "tabs/trajectory_3d_view.py", "        self._draw_timer = QTimer(self)",
           "        self._draw_timer = QTimer()", VIEW3D_TESTS, "timer not owned by the view"),
]


def _copy_worktree(dest: Path) -> None:
    files = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=REPO,
                           check=True, capture_output=True).stdout.decode().split("\0")
    for rel in filter(None, files):
        src = REPO / rel
        if src.is_file():
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)


def _pytest(copy: Path, tests: list, timeout: int = 900) -> tuple[int, str]:
    cmd = [sys.executable, "-m", "pytest", "-x", "-p", "no:cacheprovider", "-p", "no:randomly", "--tb=line", *tests]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    try:
        proc = subprocess.run(cmd, cwd=copy, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    return proc.returncode, lines[-1] if lines else ""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", help="write the results to this file")
    parser.add_argument("--only", help="comma-separated mutant ids (a partial run is reported as partial)")
    args = parser.parse_args(argv)
    selected = MUTANTS
    if args.only:
        wanted = set(args.only.split(","))
        selected = [m for m in MUTANTS if m.id in wanted]
    started = time.time()
    with tempfile.TemporaryDirectory(prefix="mutation_m46_") as tmp:
        copy = Path(tmp) / "repo"
        _copy_worktree(copy)
        all_tests = sorted({t for m in selected for t in m.tests})
        code, tail = _pytest(copy, all_tests)
        baseline = {"tests": all_tests, "exit": code, "summary": tail}
        print(f"baseline exit={code} {tail}")
        if code != 0:
            print("BASELINE FAILED - no mutant was evaluated")
            report = {"baseline": baseline, "mutants": [], "complete": False}
            if args.json:
                Path(args.json).write_text(json.dumps(report, indent=2), encoding="utf-8")
            return 2
        for m in selected:
            target = copy / m.path
            original = target.read_text(encoding="utf-8")
            occurrences = original.count(m.old)
            if occurrences != 1:
                m.result = {"status": "INVALID", "detail": f"snippet occurs {occurrences} times"}
            else:
                target.write_text(original.replace(m.old, m.new), encoding="utf-8")
                try:
                    code, tail = _pytest(copy, m.tests)
                finally:
                    target.write_text(original, encoding="utf-8")
                status = "KILLED" if code != 0 else "SURVIVED"
                m.result = {"status": status, "exit": code, "summary": tail}
            flag = " (declared equivalent)" if m.equivalent else ""
            print(f"{m.id:24s} {m.result['status']:8s}{flag}  {m.note}")
    invalid = [m.id for m in selected if m.result["status"] == "INVALID"]
    survivors = [m.id for m in selected if m.result["status"] == "SURVIVED" and not m.equivalent]
    equivalents = [m.id for m in selected if m.equivalent]
    killed = [m.id for m in selected if m.result["status"] == "KILLED"]
    complete = not args.only
    print(f"\nmutants={len(selected)} killed={len(killed)} survived_non_equivalent={len(survivors)} "
          f"declared_equivalent={len(equivalents)} invalid={len(invalid)} complete={complete} "
          f"seconds={time.time() - started:.0f}")
    if args.json:
        Path(args.json).write_text(json.dumps({
            "baseline": baseline, "complete": complete, "python": sys.version.split()[0],
            "mutants": [{"id": m.id, "path": m.path, "note": m.note, "equivalent": m.equivalent, "tests": m.tests,
                         **m.result} for m in selected],
            "killed": killed, "survived_non_equivalent": survivors, "declared_equivalent": equivalents,
            "invalid": invalid}, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if not invalid and not survivors else 1


if __name__ == "__main__":
    sys.exit(main())
