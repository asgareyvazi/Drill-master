"""Pytest plugin that writes the exact outcome of every collected test to JSON (M407).

Loaded by ``tools/quality/run_suite_sharded.py`` with ``-p pytest_outcome_recorder`` and the output path in
``DRILLMASTER_OUTCOME_JSON``. It records what pytest itself decided — collected node ids, collection errors and the
final outcome of each test (passed / failed / error / skipped / xfailed / xpassed), plus (M409) each test's
setup + call + teardown seconds — so a shard is never judged by
its process exit code or by parsing the terminal summary (which ``tests/conftest.py`` extends with its own lines).
Nothing here changes test selection, ordering, assertions or timeouts.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

_FAIL_TEXT = 4000


class OutcomeRecorder:
    def __init__(self, path: str):
        self.path = Path(path)
        self.collected: list[str] = []
        self.collection_errors: list[dict] = []
        self.outcomes: dict[str, str] = {}
        self.failures: dict[str, str] = {}
        self.exitstatus = None
        self.durations: dict[str, float] = {}

    # -- collection ---------------------------------------------------------------------------------------------
    def pytest_collectreport(self, report):
        if report.failed:
            self.collection_errors.append({"nodeid": report.nodeid, "text": str(report.longrepr)[:_FAIL_TEXT]})

    def pytest_collection_finish(self, session):
        self.collected = [item.nodeid for item in session.items]

    # -- run ----------------------------------------------------------------------------------------------------
    def pytest_runtest_logreport(self, report):
        nodeid = report.nodeid
        # M409: wall time per test = setup + call + teardown (pytest's own report.duration)
        self.durations[nodeid] = self.durations.get(nodeid, 0.0) + float(getattr(report, "duration", 0.0) or 0.0)
        wasxfail = hasattr(report, "wasxfail")
        if report.when == "call":
            if wasxfail:
                outcome = "xfailed" if report.skipped else "xpassed"
            else:
                outcome = report.outcome          # passed / failed / skipped
            self._set(nodeid, outcome, report)
        elif report.when == "setup":
            if report.skipped:
                self._set(nodeid, "xfailed" if wasxfail else "skipped", report)
            elif report.failed:
                self._set(nodeid, "error", report)
        elif report.when == "teardown" and report.failed:
            # A teardown error after a pass is still an error for that test.
            self._set(nodeid, "error", report, keep_failed=True)

    def _set(self, nodeid, outcome, report, keep_failed=False):
        if keep_failed and self.outcomes.get(nodeid) == "failed":
            return
        self.outcomes[nodeid] = outcome
        if outcome in ("failed", "error"):
            self.failures[nodeid] = str(report.longrepr)[-_FAIL_TEXT:]

    def pytest_sessionfinish(self, session, exitstatus):
        self.exitstatus = int(exitstatus)
        counts: dict[str, int] = {}
        for outcome in self.outcomes.values():
            counts[outcome] = counts.get(outcome, 0) + 1
        not_run = [nodeid for nodeid in self.collected if nodeid not in self.outcomes]
        payload = {
            "collected": len(self.collected),
            "counts": counts,
            "not_run": not_run,
            "collection_errors": self.collection_errors,
            "failures": self.failures,
            "skipped": sorted(n for n, o in self.outcomes.items() if o == "skipped"),
            "xfailed": sorted(n for n, o in self.outcomes.items() if o == "xfailed"),
            "xpassed": sorted(n for n, o in self.outcomes.items() if o == "xpassed"),
            "pytest_exitstatus": self.exitstatus,
            "durations": {nodeid: round(sec, 4) for nodeid, sec in self.durations.items()},
        }
        self.path.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")


def pytest_configure(config):
    path = os.environ.get("DRILLMASTER_OUTCOME_JSON")
    if path:
        config.pluginmanager.register(OutcomeRecorder(path), "drillmaster_outcome_recorder")
