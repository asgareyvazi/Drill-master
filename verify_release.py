"""Release verification for DrillMaster (no GUI required).

The release gate compiles the repository, verifies pytest collection, and then
executes the complete pytest suite using the repository's ``pyproject.toml``
configuration. Pytest's built-in unittest collector keeps existing unittest
TestCase tests in the release gate.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parent


_SUMMARY_NAMES = (
    "passed",
    "failed",
    "skipped",
    "error",
    "errors",
    "xfailed",
    "xpassed",
    "deselected",
)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a release command, echoing its output without hiding failures."""
    print("$", " ".join(command))
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    if output:
        print(output, end="" if output.endswith("\n") else "\n")
    return completed


def run(command: list[str]) -> int:
    """Backward-compatible command runner returning a process code."""
    return _run(command).returncode


def _collected_count(output: str) -> int:
    """Count per-file collection totals emitted by ``pytest --collect-only -q``."""
    total = 0
    for line in output.splitlines():
        match = re.match(r"^.+\.py:\s+(\d+)\s*$", line.strip())
        if match:
            total += int(match.group(1))
    return total


def _pytest_counts(output: str) -> Dict[str, int]:
    """Extract the final pytest result counts without assuming a test total."""
    counts = {name: 0 for name in _SUMMARY_NAMES}
    summary = ""
    for line in reversed(output.splitlines()):
        if any(re.search(rf"\b\d+\s+{name}\b", line) for name in _SUMMARY_NAMES):
            summary = line
            break
    for name in _SUMMARY_NAMES:
        match = re.search(rf"\b(\d+)\s+{name}\b", summary)
        if match:
            counts[name] = int(match.group(1))
    return counts


def run_pytest() -> bool:
    """Collect and execute the complete pytest suite using project config."""
    collect = _run([sys.executable, "-m", "pytest", "--collect-only", "-q"])
    if collect.returncode != 0:
        print("Release verification failed: pytest collection failed.")
        return False

    collected = _collected_count((collect.stdout or "") + (collect.stderr or ""))
    if collected <= 0:
        print("Release verification failed: pytest collected no tests.")
        return False

    result = _run([sys.executable, "-m", "pytest", "-ra"])
    output = (result.stdout or "") + (result.stderr or "")
    counts = _pytest_counts(output)
    print(
        "Pytest release counts: "
        f"collected={collected}, "
        f"passed={counts['passed']}, "
        f"skipped={counts['skipped']}, "
        f"failed={counts['failed']}, "
        f"errors={counts['error'] + counts['errors']}, "
        f"xfailed={counts['xfailed']}, "
        f"xpassed={counts['xpassed']}, "
        f"deselected={counts['deselected']}"
    )

    if result.returncode != 0 or counts["failed"] or counts["error"] or counts["errors"]:
        print("Release verification failed: pytest reported failures or errors.")
        return False
    return True


def main() -> int:
    compile_targets = [
        "core",
        "dialogs",
        "tabs",
        "tests",
        "packaging",
        "app.py",
        "main_window.py",
        "run.py",
        "verify_release.py",
        "reset_database.py",
    ]
    compile_result = _run([sys.executable, "-m", "compileall", "-q", *compile_targets])
    if compile_result.returncode != 0:
        print("Release verification failed: syntax compilation failed.")
        return 1
    if not run_pytest():
        return 1
    print("Release verification passed: syntax + complete pytest regression suite")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
