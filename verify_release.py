"""Deterministic source-release gate; NOT Windows/installer/real-DDR acceptance.

Checks Git identity/state, exact runtime pins, resources, lint ratchet, compile,
pytest accounting and wheel contents. Optional integration skips are reported
by pytest; they do not become production acceptance. Use --allow-dirty only
for an explicitly identified development worktree.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import re
import tempfile
import zipfile
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


def _run(command: list[str], *, echo=True, cwd=None) -> subprocess.CompletedProcess[str]:
    """Run a release command, echoing its output without hiding failures."""
    print("$", " ".join(command))
    completed = subprocess.run(
        command,
        cwd=cwd or ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    if output and echo:
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


# These tests are external acceptance, never repository PASS evidence. A new
# skip (including a missing core import) blocks the repository source gate.
OPTIONAL_ACCEPTANCE_SKIPS = {
    ("test_ddr_acceptance", "test_real_ddr_excel_canonical_ir_review_and_atomic_db"):
        "DRILLMASTER_TEST_DDR_XLSX is not set; real DDR acceptance is opt-in",
    ("test_ddr_acceptance", "test_real_ddr_pdf_mineru_common_ir_review_and_atomic_db"):
        "DRILLMASTER_TEST_DDR_PDF is not set; real DDR acceptance is opt-in",
    ("test_mineru_real_integration", "test_real_mineru_parse_and_normalize"):
        "Set MINERU_INTEGRATION_INPUT to run against a real MinerU installation",
    ("test_packaging_smoke", "test_real_windows_bundle_smoke_when_provided"):
        "Windows bundle not available in this environment",
}


def validate_pytest_report(path, collected, counts):
    """Independently reconcile per-test JUnit records and reasoned skip policy."""
    import xml.etree.ElementTree as ET
    try:
        cases = ET.parse(path).findall(".//testcase")
    except (OSError, ET.ParseError):
        print("FAIL: missing or malformed pytest execution report")
        return False
    seen, actual = set(), {"passed": 0, "skipped": 0}
    for case in cases:
        identity = (case.get("classname", ""), case.get("name", ""))
        if not all(identity) or identity in seen or case.find("failure") is not None or case.find("error") is not None:
            return False
        seen.add(identity)
        skipped = case.find("skipped")
        if skipped is None:
            actual["passed"] += 1
            continue
        key = (identity[0].rsplit(".", 1)[-1], identity[1])
        if key not in OPTIONAL_ACCEPTANCE_SKIPS or skipped.get("message") != OPTIONAL_ACCEPTANCE_SKIPS[key]:
            print(f"FAIL: unexpected skip {identity}: {skipped.get('message')}")
            return False
        actual["skipped"] += 1
        print(f"NOT-RUN external acceptance (SKIPPED-OPTIONAL in source gate): {identity}")
    return len(cases) == collected and all(actual[k] == counts[k] for k in actual)


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

    with tempfile.TemporaryDirectory(prefix="drillmaster-pytest-") as directory:
        report = Path(directory) / "results.xml"
        result = _run([sys.executable, "-m", "pytest", "-ra", f"--junitxml={report}"])
        output = (result.stdout or "") + (result.stderr or "")
        report_valid = validate_pytest_report(report, collected, _pytest_counts(output))
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
    if not report_valid:
        return False
    executed = sum(counts[name] for name in ("passed", "skipped", "failed", "error", "errors", "xfailed", "xpassed"))
    if counts["xfailed"] or counts["xpassed"] or counts["deselected"] or executed != collected:
        print("Release verification failed: unexpected xfail/xpass/deselection or collection/execution mismatch.")
        return False
    return True


def verify_repository(expected_sha=None, allow_dirty=False) -> bool:
    head = _run(["git", "rev-parse", "HEAD"])
    state = _run(["git", "status", "--porcelain=v1", "--untracked-files=all"])
    branch = _run(["git", "branch", "--show-current"])
    if any(result.returncode for result in (head, state, branch)):
        return False
    if expected_sha and head.stdout.strip() != expected_sha:
        print("FAIL: HEAD does not match the full expected SHA")
        return False
    if state.stdout.strip() and not allow_dirty:
        print("FAIL: dirty worktree; --allow-dirty identifies a development run, not a clean release")
        return False
    return _run(["git", "diff", "--check"]).returncode == 0 and _run(
        ["git", "diff", "--cached", "--check"]).returncode == 0


def verify_dependencies() -> bool:
    from packaging.requirements import Requirement
    errors = []
    for line in (ROOT / "requirements-lock.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        requirement = Requirement(line)
        try:
            installed = importlib.metadata.version(requirement.name)
        except importlib.metadata.PackageNotFoundError:
            installed = "NOT INSTALLED"
        print(f"Dependency: {requirement.name} {installed} (required {requirement.specifier})")
        if installed == "NOT INSTALLED" or installed not in requirement.specifier:
            errors.append(requirement.name)
    return not errors and _run([sys.executable, "-m", "pip", "check"]).returncode == 0


def verify_resources() -> bool:
    required = ("config/ai_models.json", "config/company_templates/oeoc.json", "templates/OEOC_DDR_v3.json",
                "packaging/DrillMaster.spec", "packaging/build_windows.ps1", "packaging/DrillMaster.iss")
    for relative in required:
        path = ROOT / relative
        if not path.is_file():
            print(f"FAIL: missing resource {relative}")
            return False
        if path.suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))
    return True


def verify_version() -> bool:
    """Check source, wheel configuration and Windows version inputs agree."""
    import ast
    from packaging.version import Version, InvalidVersion
    try:
        tree = ast.parse((ROOT / "core/version.py").read_text(encoding="utf-8"))
        value = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == "__version__" for t in n.targets))
        version = Version(value)
        if version.is_prerelease or len(version.release) != 3:
            return False
        import tomllib
        config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        valid = config["tool"]["setuptools"]["dynamic"]["version"]["attr"] == "core.version.__version__"
        app_tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
        bindings = [n.value for n in ast.walk(app_tree) if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "APP_VERSION" for t in n.targets)]
        valid = valid and len(bindings) == 1 and isinstance(bindings[0], ast.Name) and bindings[0].id == "__version__"
        for file in ("app.py", "packaging/DrillMaster.spec"):
            parsed = ast.parse((ROOT / file).read_text(encoding="utf-8"))
            valid = valid and any(isinstance(n, ast.ImportFrom) and n.module == "core.version"
                                  and any(a.name == "__version__" and a.asname is None for a in n.names)
                                  for n in ast.walk(parsed))
        inputs = {"packaging/build_windows.ps1": "core\\version.py",
                  "packaging/DrillMaster.iss": "AppVersion={#AppVersion}"}
        valid = valid and all(token in (ROOT / file).read_text(encoding="utf-8") for file, token in inputs.items())
        print(f"Source/packaging version: {value}; consistent={valid}")
        return valid
    except (OSError, SyntaxError, ValueError, KeyError, StopIteration, InvalidVersion):
        return False


def verify_lint() -> bool:
    # Preserve the historical ratchet population and pinned rule implementation.
    if importlib.metadata.version("ruff") != "0.16.6":
        print("FAIL: lint ratchet requires ruff==0.16.6")
        return False
    defects = _run([sys.executable, "-m", "ruff", "check", "--select", "E722,F821", "."])
    debt = _run([sys.executable, "-m", "ruff", "check", "--output-format", "json",
                 "core", "dialogs", "tabs", "tests"], echo=False)
    if debt.returncode not in (0, 1) or defects.returncode:
        return False
    count = len(json.loads(debt.stdout))
    ceiling = int((ROOT / ".github/ruff-debt-ceiling.txt").read_text(encoding="utf-8").strip())
    print(f"Lint debt: {count}; ceiling: {ceiling} (not lint-clean)")
    return count <= ceiling


def verify_wheel() -> bool:
    with tempfile.TemporaryDirectory(prefix="drillmaster-wheel-") as directory:
        import shutil
        tracked = _run(["git", "ls-files", "-z"], echo=False)
        if tracked.returncode:
            return False
        source = Path(directory) / "source"
        source.mkdir()
        for name in tracked.stdout.split("\0"):
            if name and (ROOT / name).is_file():
                target = source / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / name, target)
        # Never let stale build/lib files mask an omitted package.
        result = _run([sys.executable, "-m", "build", "--wheel", "--outdir", directory], cwd=source)
        if result.returncode:
            return False
        wheels = list(Path(directory).glob("*.whl"))
        if len(wheels) != 1:
            return False
        with zipfile.ZipFile(wheels[0]) as wheel:
            names = set(wheel.namelist())
            from email.parser import Parser
            from core.version import __version__
            metadata = [n for n in names if n.endswith(".dist-info/METADATA")]
            if len(metadata) != 1 or Parser().parsestr(wheel.read(metadata[0]).decode())["Version"] != __version__:
                return False
            required = {"app.py", "main_window.py", "core/database.py", "ui/helper.py", "ui/utils.py",
                        "config/ai_models.json", "config/company_templates/oeoc.json", "templates/OEOC_DDR_v3.json"}
            if not required <= names or any(name.startswith("tests/") for name in names):
                return False
        installed = Path(directory) / "installed"
        install = _run([sys.executable, "-m", "pip", "install", "--no-deps", "--no-index",
                        "--target", str(installed), str(wheels[0])])
        if install.returncode:
            return False
        # Crucially run OUTSIDE the checkout: source-path imports used to hide
        # the missing ui package in apparently successful wheel checks.
        return _run([sys.executable, str(installed / "app.py"), "--package-smoke"],
                    cwd=directory).returncode == 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-sha", help="full SHA expected at HEAD")
    parser.add_argument("--allow-dirty", action="store_true", help="development-only worktree verification")
    args = parser.parse_args(argv)
    print(f"Environment: Python {sys.version}; platform={sys.platform}; "
          f"Qt={os.getenv('QT_QPA_PLATFORM', 'default')}; "
          f"Qt stub directory={os.getenv('QT_STUB_DIR', 'not declared')}")
    if not verify_repository(args.expected_sha, args.allow_dirty):
        return 1
    for check in (verify_dependencies, verify_resources, verify_version, verify_lint):
        if not check():
            print(f"FAIL: {check.__name__}")
            return 1
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
    if not verify_wheel():
        print("FAIL: wheel packaging")
        return 1
    print("VERIFIED: source gate only. Windows EXE/installer, real MinerU/DDR and production DB acceptance NOT certified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
