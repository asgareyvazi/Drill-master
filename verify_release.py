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
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent

# Coverage floor (opt-in with --coverage; CI enables it on one matrix leg).
# The population is every *tracked* product module, so files that no test
# imports count as 0 % instead of silently leaving the denominator.
COVERAGE_VERSION = "7.16.2"
COVERAGE_FLOOR = ".github/coverage-floor.json"
COVERAGE_POPULATION = (
    "core/", "dialogs/", "tabs/", "ui/", "config/",
    "app.py", "main_window.py", "run.py", "reset_database.py",
)


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


def _run(command: list[str], *, echo=True, cwd=None, env=None) -> subprocess.CompletedProcess[str]:
    """Run a release command, echoing its output without hiding failures."""
    print("$", " ".join(command))
    completed = subprocess.run(
        command,
        cwd=cwd or ROOT,
        check=False,
        text=True,
        capture_output=True,
        env=env,
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


# M124: a test still running after this many seconds is a hang (tests/conftest.py watchdog).  The slowest
# bounded test, the M122 CPU-load cancel test, is bounded at about 405 s of waits (15 cycles x (15 s + 10 s)
# + 10 s + 20 s); 900 s leaves room for slow CI runners and coverage tracing and still ends a hang before
# the job timeout, which would cancel the job and lose all captured output.
TEST_HANG_SECONDS = 900
# Not anchored: pytest's progress marks share the line the dump starts on (".Timeout (0:15:00)!").  Only
# progress marks may precede it: a child process's dump quoted in a failure message ("E   ... Timeout (")
# belongs to that test's own failure, not to a hang of this pytest process (M134: a D46 child dump was
# reported as "pytest hang ... process ended").
_HANG_HEADER = re.compile(r"Timeout \((?P<after>[0-9:.]+)\)!")
_PROGRESS_MARKS = re.compile(r"[.sFEfxXR]*")
_HANG_FRAME = re.compile(r'File "(?P<path>[^"]+)", line (?P<line>\d+) in (?P<name>\S+)')


def _short_path(path: str) -> str:
    normal = path.replace("\\", "/")
    for marker in ("/tests/", "/core/", "/tabs/", "/dialogs/"):
        at = normal.rfind(marker)
        if at >= 0:
            return normal[at + 1:]
    return normal.rsplit("/", 1)[-1]


def _dump_threads(output: str):
    """(header match, [frames per thread]) of this process's watchdog dump, or (None, []).

    Threads are in dump order, frames most recent call first; a thread without a Python frame (a Qt or
    other native thread, or one in native code only) is kept as an empty list.
    """
    text = output or ""
    header = None
    for match in _HANG_HEADER.finditer(text):
        line_start = text.rfind("\n", 0, match.start()) + 1
        if _PROGRESS_MARKS.fullmatch(text[line_start:match.start()]):
            header = match
            break
    if header is None:
        return None, []
    threads, current = [], None
    for line in text[header.end():].splitlines():
        if line.startswith(("Thread 0x", "Current thread 0x")):
            current = []
            threads.append(current)
            continue
        frame = _HANG_FRAME.search(line)
        if frame and current is not None:
            current.append(frame)
    return header, threads


def describe_hang(output: str) -> Optional[str]:
    """One line naming the hung test from a faulthandler watchdog dump, or None when there is none.

    The dump lists every thread, most recent call first.  The test function's frame is the one directly
    above pytest's ``pytest_pyfunc_call``; the innermost frame reported is the top of THAT thread (where
    the test is blocked).  A hang in a fixture falls back to the first frame under tests/.
    """
    header, threads = _dump_threads(output)
    if header is None:
        return None
    test, blocked = None, None
    for frames in threads:
        for index, frame in enumerate(frames):
            if frame["name"] == "pytest_pyfunc_call" and index > 0:
                test, blocked = frames[index - 1], frames[0]
                break
        if test is not None:
            break
    if test is None:
        for frames in threads:
            test = next((f for f in frames if "/tests/" in f["path"].replace("\\", "/")), None)
            if test is not None:
                blocked = frames[0]
                break

    def where(frame):
        return f"{_short_path(frame['path'])}:{frame['line']} in {frame['name']}" if frame else "not found"
    return (f"a test did not finish within {header['after']} (faulthandler watchdog, process ended); "
            f"test frame: {where(test)}; blocked in: {where(blocked)}")


def describe_hang_threads(output: str, frames_per_thread: int = 3) -> Optional[str]:
    """Every thread of the watchdog dump on one line, or None when there is no dump (M134, D51).

    ``describe_hang`` names the hung test; a hang is often caused by ANOTHER thread (a lock or GIL
    holder), so this lists each thread's innermost frames, innermost first and joined by " < ".  The
    thread running the test is marked "(test)"; a thread with no Python frame is reported as such.
    """
    header, threads = _dump_threads(output)
    if header is None:
        return None
    parts = []
    for number, frames in enumerate(threads, 1):
        is_test = any(f["name"] == "pytest_pyfunc_call" for f in frames)
        chain = " < ".join(f"{_short_path(f['path'])}:{f['line']} {f['name']}" for f in frames[:frames_per_thread])
        parts.append(f"T{number}{' (test)' if is_test else ''}: {chain or 'no Python frame'}")
    return f"{len(threads)} thread(s): " + " | ".join(parts)


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
            _ci_error("unexpected skip", f"{identity}: {skipped.get('message')}")
            return False
        actual["skipped"] += 1
        print(f"NOT-RUN external acceptance (SKIPPED-OPTIONAL in source gate): {identity}")
    return len(cases) == collected and all(actual[k] == counts[k] for k in actual)


def _annotation_text(text, limit=300):
    """One line, escaped for a GitHub Actions workflow command."""
    line = " ".join(str(text or "").split())[:limit]
    return line.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def annotate_failures(path, environ=None) -> int:
    """Emit one ``::error`` annotation per failed/errored JUnit case in CI.

    Job logs are not always retrievable, but check-run annotations are; this
    names the failing tests there. Diagnostics only: it never changes the gate
    result. Messages are truncated to one short line.
    """
    environ = os.environ if environ is None else environ
    if environ.get("GITHUB_ACTIONS") != "true" or not Path(path).is_file():
        return 0
    import xml.etree.ElementTree as ET
    try:
        cases = ET.parse(path).findall(".//testcase")
    except ET.ParseError as exc:
        print(f"::error title=pytest report::{_annotation_text(exc)}")
        return 1
    emitted = 0
    for case in cases:
        for kind in ("failure", "error"):
            problem = case.find(kind)
            if problem is None:
                continue
            identity = f"{case.get('classname', '')}::{case.get('name', '')}"
            lines = (problem.text or "").strip().splitlines()
            message = problem.get("message") or (lines[-1] if lines else "")
            print(f"::error title=pytest {kind}::{_annotation_text(identity, 200)} - {_annotation_text(message)}")
            emitted += 1
    return emitted


_WARNING_LINE = re.compile(r"^\s+(?P<where>.+?):(?P<line>\d+): (?P<category>\w*Warning): (?P<message>.*)$")


_COLLAPSED_HEADER = re.compile(r"^(?P<path>\S.*?): (?P<count>\d+) warnings?$")
_PYTEST_OUTCOME = re.compile(r"\b\d+ (passed|failed|errors?|skipped|deselected|xfailed|xpassed)\b")
_PYTEST_TOTAL = re.compile(r"\b(?P<count>\d+) warnings?\b")


def summarize_warnings(output: str) -> List[Tuple[int, str, str, str, str]]:
    """Group pytest's "warnings summary" into (count, origin, category, location, message).

    A block lists the locations of its occurrences followed by the indented
    ``path:line: Category: message`` line.  Fewer than ten locations are listed
    one per occurrence; from ten on pytest collapses them into
    ``file: N warnings`` lines (M105 fix: those count N, not 1).  Every summary
    section is read, including "warnings summary (final)".  ``origin`` is
    ``third-party`` (site-packages, frozen or standard-library modules) or
    ``repository``.  Diagnostics only: the gate never depends on it.
    """
    groups: Dict[Tuple[str, str, str, str], int] = {}
    headers = 0
    inside = False
    for line in output.splitlines():
        if line.startswith("="):
            inside = "warnings summary" in line
            headers = 0
            continue
        if not inside:
            continue
        if line.startswith("-- Docs:"):
            inside = False
            continue
        if not line.strip():
            headers = 0
            continue
        match = _WARNING_LINE.match(line)
        if match:
            where = match["where"].replace("\\", "/")
            third = "site-packages" in where or where.startswith("<") or "/lib/python" in where
            if "site-packages/" in where:
                where = where.split("site-packages/", 1)[1]
            key = ("third-party" if third else "repository", match["category"], f"{where}:{match['line']}",
                   match["message"].strip()[:160])
            groups[key] = groups.get(key, 0) + max(headers, 1)
            headers = 0
        elif not line.startswith(" "):
            collapsed = _COLLAPSED_HEADER.match(line.strip())
            headers += int(collapsed["count"]) if collapsed else 1
    return sorted(((count, *key) for key, count in groups.items()), key=lambda row: (-row[0], row[1:]))


def pytest_reported_warnings(output: str) -> Optional[int]:
    """The warning count on pytest's final summary line (None when it reports none)."""
    for line in reversed(output.splitlines()):
        if _PYTEST_OUTCOME.search(line):
            match = _PYTEST_TOTAL.search(line)
            return int(match["count"]) if match else None
    return None


def report_warnings(output: str, environ=None, limit: int = 8) -> int:
    """Print the grouped warning inventory; in CI also emit up to ``limit`` notices."""
    environ = os.environ if environ is None else environ
    rows = summarize_warnings(output)
    total = sum(row[0] for row in rows)
    reported = pytest_reported_warnings(output)
    reconciled = "matches" if reported == total or (reported is None and total == 0) else "DIFFERS from"
    print(f"Pytest warning inventory: {total} occurrence(s) in {len(rows)} group(s); "
          f"{reconciled} pytest's own total ({reported if reported is not None else 0})")
    for count, origin, category, location, message in rows:
        print(f"  {count:5d}  {origin:11s}  {category}  {location}  {message}")
    if environ.get("GITHUB_ACTIONS") == "true" and rows:
        by_origin = {}
        for count, origin, *_rest in rows:
            by_origin[origin] = by_origin.get(origin, 0) + count
        print(f"::notice title=pytest warnings::{_annotation_text(f'{total} occurrence(s), {len(rows)} group(s) ({reconciled} pytest total {reported}); ' + ', '.join(f'{k}: {v}' for k, v in sorted(by_origin.items())))}")
        for count, origin, category, location, message in rows[:limit - 1]:
            print(f"::notice title=pytest warning group::{_annotation_text(f'{count}x {origin} {category} {location}: {message}')}")
    return total


def _ci_error(title, text, limit: int = 300) -> None:
    """Also surface a gate failure reason as a CI annotation (diagnostics only)."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::error title={_annotation_text(title, 60)}::{_annotation_text(text, limit)}")


def run_pytest(coverage_data: Path | None = None) -> bool:
    """Collect and execute the complete pytest suite using project config.

    With ``coverage_data`` the same pytest invocation runs under
    ``coverage run`` (configured in pyproject.toml) and writes its data there.
    """
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
        runner = [sys.executable, "-m"]
        if coverage_data is not None:
            runner += ["coverage", "run", f"--data-file={coverage_data}", "-m"]
        env = dict(os.environ)
        env.setdefault("DRILLMASTER_TEST_HANG_SECONDS", str(TEST_HANG_SECONDS))
        result = _run([*runner, "pytest", "-ra", f"--junitxml={report}"], env=env)
        output = (result.stdout or "") + (result.stderr or "")
        hang = describe_hang(output)
        if hang:
            print(f"Release verification failed: {hang}")
            _ci_error("pytest hang", hang)
            # D51: the job log is not retrievable, so every thread's innermost frames go into an annotation.
            _ci_error("pytest hang threads", describe_hang_threads(output), limit=2000)
        report_valid = validate_pytest_report(report, collected, _pytest_counts(output))
        annotate_failures(report)
    output = (result.stdout or "") + (result.stderr or "")
    counts = _pytest_counts(output)
    report_warnings(output)
    summary = (
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
    print(summary)

    if result.returncode != 0 or counts["failed"] or counts["error"] or counts["errors"]:
        print("Release verification failed: pytest reported failures or errors.")
        _ci_error("pytest", summary)
        return False
    if not report_valid:
        _ci_error("pytest report", "JUnit report did not reconcile; " + summary)
        return False
    executed = sum(counts[name] for name in ("passed", "skipped", "failed", "error", "errors", "xfailed", "xpassed"))
    if counts["xfailed"] or counts["xpassed"] or counts["deselected"] or executed != collected:
        print("Release verification failed: unexpected xfail/xpass/deselection or collection/execution mismatch.")
        _ci_error("pytest accounting", f"collected={collected}; " + summary)
        return False
    return True


def tracked_product_sources() -> list[str]:
    """Tracked Python files of the coverage population (``git ls-files``)."""
    listed = _run(["git", "ls-files", "-z", "--", "*.py"], echo=False)
    if listed.returncode != 0:
        raise RuntimeError("git ls-files failed")
    return sorted(p for p in listed.stdout.split("\0") if p.startswith(COVERAGE_POPULATION))


def evaluate_coverage(report: dict, tracked: list[str], floor: float) -> tuple[bool, str]:
    """Branch+line coverage over exactly the tracked product files.

    Fails when any tracked file is missing from the report: an unmeasured
    file would otherwise shrink the denominator and inflate the figure.
    """
    if not tracked:
        return False, "coverage: no tracked product sources found"
    files = {Path(name).as_posix(): data["summary"] for name, data in report.get("files", {}).items()}
    missing = [name for name in tracked if name not in files]
    if missing:
        return False, (f"coverage denominator incomplete: {len(missing)} tracked product file(s) "
                       f"absent from the report, e.g. {', '.join(missing[:3])}")
    covered = sum(files[n]["covered_lines"] + files[n].get("covered_branches", 0) for n in tracked)
    total = sum(files[n]["num_statements"] + files[n].get("num_branches", 0) for n in tracked)
    percent = 100.0 * covered / total if total else 0.0
    message = (f"product coverage (branch+line) {percent:.2f}% over {len(tracked)} tracked files "
               f"({covered}/{total}); floor {floor:.2f}%")
    return round(percent, 2) >= floor, message


def verify_coverage(coverage_data: Path) -> bool:
    """Enforce the non-decreasing floor in .github/coverage-floor.json."""
    try:
        floor = float(json.loads((ROOT / COVERAGE_FLOOR).read_text(encoding="utf-8"))["percent"])
        tracked = tracked_product_sources()
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print(f"FAIL: coverage floor configuration: {exc}")
        return False
    with tempfile.TemporaryDirectory(prefix="drillmaster-coverage-json-") as directory:
        target = Path(directory) / "coverage.json"
        exported = _run([sys.executable, "-m", "coverage", "json", f"--data-file={coverage_data}",
                         "-o", str(target), "-q"])
        if exported.returncode != 0 or not target.is_file():
            print("FAIL: coverage report could not be exported")
            return False
        report = json.loads(target.read_text(encoding="utf-8"))
    ok, message = evaluate_coverage(report, tracked, floor)
    print(("" if ok else "FAIL: ") + message)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::notice title=coverage::{_annotation_text(message)}")
    if not ok:
        _ci_error("coverage", message)
    return ok


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
    print(f"Lint debt: {count}; ceiling: {ceiling} ({'lint-clean' if count == 0 else 'not lint-clean'})")
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
    parser.add_argument("--coverage", action="store_true",
                        help=f"run pytest under coverage and enforce {COVERAGE_FLOOR}")
    args = parser.parse_args(argv)
    print(f"Environment: Python {sys.version}; platform={sys.platform}; "
          f"Qt={os.getenv('QT_QPA_PLATFORM', 'default')}; "
          f"Qt stub directory={os.getenv('QT_STUB_DIR', 'not declared')}")
    if not verify_repository(args.expected_sha, args.allow_dirty):
        _ci_error("release gate", "repository verification failed")
        return 1
    for check in (verify_dependencies, verify_resources, verify_version, verify_lint):
        if not check():
            print(f"FAIL: {check.__name__}")
            _ci_error("release gate", f"{check.__name__} failed")
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
        _ci_error("release gate", "syntax compilation failed")
        return 1
    if args.coverage:
        try:
            installed = importlib.metadata.version("coverage")
        except importlib.metadata.PackageNotFoundError:
            installed = "not installed"
        if installed != COVERAGE_VERSION:
            print(f"FAIL: --coverage requires coverage=={COVERAGE_VERSION} (found {installed})")
            _ci_error("release gate", "coverage tool missing or not pinned")
            return 1
        with tempfile.TemporaryDirectory(prefix="drillmaster-coverage-") as directory:
            data = Path(directory) / ".coverage"
            if not run_pytest(coverage_data=data):
                _ci_error("release gate", "pytest stage failed (see the pytest annotations)")
                return 1
            if not verify_coverage(data):
                _ci_error("release gate", "coverage floor failed")
                return 1
    elif not run_pytest():
        _ci_error("release gate", "pytest stage failed (see the pytest annotations)")
        return 1
    if not verify_wheel():
        print("FAIL: wheel packaging")
        _ci_error("release gate", "wheel packaging stage failed")
        return 1
    print("VERIFIED: source gate only. Windows EXE/installer, real MinerU/DDR and production DB acceptance NOT certified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
