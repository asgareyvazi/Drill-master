"""The release boundary: what ships must be able to start.

A green suite run *inside the checkout* proves nothing about the artifact: the checkout has every
loose file on disk, including files that were never added to the index. This module tests the
artifact instead — the population a release is actually built from (``git ls-files``):

1. ``test_runtime_import_closure_is_tracked`` — every project module reachable from the release
   entry point (``app:main``) exists *in the index*, not merely in the working tree.
2. ``test_wheel_from_tracked_population_starts`` — build the wheel from the tracked population,
   confirm every required module is inside it, install it into an isolated target directory and
   start the application's own ``--package-smoke`` entry point from a directory that is not the
   checkout, with the checkout absent from ``sys.path``.

Both tests fail if a required module stops being tracked — that is the defect class this guards and
it is reproduced by ``git rm --cached core/operational_time.py`` before running them.
"""
from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Namespaces the built distribution ships (pyproject: packages.find include + py-modules).
SHIPPED_PACKAGES = ("core", "dialogs", "tabs", "ui", "config", "templates")
SHIPPED_MODULES = ("app", "main_window", "run")
ENTRY_MODULES = ("app",)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def tracked_python_files() -> set[str]:
    """Every tracked ``.py`` file, relative to the repository root."""
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    return {name for name in out.decode().split("\0") if name.endswith(".py")}


def _module_path(module: str) -> str:
    return module.replace(".", "/") + ".py"


def _package_init(module: str) -> str:
    return module.replace(".", "/") + "/__init__.py"


def _resolve_imports(path: Path, module: str) -> set[str]:
    """Project modules imported by one file (absolute and relative imports)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:                                   # pragma: no cover - compileall catches these
        return set()
    package_parts = module.split(".")[:-1]                # the package the file lives in
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package_parts[: len(package_parts) - node.level + 1]
                name = ".".join([*base, node.module]) if node.module else ".".join(base)
            else:
                name = node.module or ""
            if name:
                found.add(name)
                for alias in node.names:                  # ``from core import database``
                    if alias.name != "*":
                        found.add(f"{name}.{alias.name}")
    return found


def _is_shipped(module: str) -> bool:
    root = module.split(".")[0]
    return root in SHIPPED_PACKAGES or root in SHIPPED_MODULES


def _shipped_file(module: str) -> Path | None:
    """The file that would satisfy an import of ``module`` in a source tree, if any."""
    for candidate in (_module_path(module), _package_init(module)):
        if (ROOT / candidate).is_file():
            return ROOT / candidate
    return None


def runtime_import_closure() -> set[str]:
    """Project modules reachable from the release entry point, as files, transitively."""
    required_files: set[str] = set()
    pending = [m for m in ENTRY_MODULES if _shipped_file(m)]
    seen: set[str] = set()
    while pending:
        module = pending.pop()
        if module in seen or not _is_shipped(module):
            continue
        seen.add(module)
        path = _shipped_file(module)
        if path is None:
            continue
        required_files.add(str(path.relative_to(ROOT)))
        for imported in _resolve_imports(path, module):
            if _is_shipped(imported) and imported not in seen:
                pending.append(imported)
    return required_files


def _copy_tracked_population(destination: Path) -> list[str]:
    """Copy exactly the tracked files into a throwaway tree — this is the release population."""
    names = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True,
                           check=True).stdout.decode().split("\0")
    copied = []
    for name in names:
        if not name:
            continue
        source = ROOT / name
        if not source.is_file():
            continue
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(name)
    return copied


def _build_wheel(source: Path, outdir: Path) -> Path:
    """Build a wheel the way the project's release gate does (python -m build)."""
    cmd = [sys.executable, "-m", "build", "--wheel", "--outdir", str(outdir)]
    proc = subprocess.run(cmd, cwd=source, capture_output=True, text=True)
    if proc.returncode != 0:
        # Fall back to an isolated build when the running interpreter lacks the build requires.
        proc = subprocess.run(cmd, cwd=source, capture_output=True, text=True,
                              env={**os.environ, "PIP_DISABLE_PIP_VERSION_CHECK": "1"})
    wheels = sorted(outdir.glob("*.whl"))
    assert proc.returncode == 0 and len(wheels) == 1, (
        f"wheel build failed (exit {proc.returncode}):\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")
    return wheels[0]


@pytest.fixture(scope="module")
def built_wheel() -> tuple[Path, set[str]]:
    """A wheel built from the tracked population, plus the files that went into it."""
    with tempfile.TemporaryDirectory(prefix="drillmaster-release-boundary-") as tmp:
        tmp_path = Path(tmp)
        source = tmp_path / "source"
        source.mkdir()
        copied = set(_copy_tracked_population(source))
        outdir = tmp_path / "dist"
        outdir.mkdir()
        wheel = _build_wheel(source, outdir)
        yield wheel, copied


def test_runtime_import_closure_is_tracked():
    """A module the entry point needs must be in the index, not only on the developer's disk."""
    required = runtime_import_closure()
    assert required, "the import closure of app:main came back empty — the walker is broken"
    tracked = tracked_python_files()
    untracked = sorted(m for m in required if m not in tracked)
    assert not untracked, (
        "these modules are required by the release entry point but are NOT tracked, so no "
        f"artifact built from the index can contain them: {untracked}")


def test_wheel_from_tracked_population_starts(built_wheel):
    """The artifact must contain every required module and start outside the checkout."""
    wheel, copied = built_wheel
    required = runtime_import_closure()

    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
    missing_from_wheel = sorted(m for m in required if m not in names)
    assert not missing_from_wheel, (
        f"the wheel built from the tracked population omits required modules: {missing_from_wheel}")

    assert any(n.endswith(".dist-info/METADATA") for n in names), "wheel has no METADATA"
    assert any(n.endswith(".dist-info/RECORD") for n in names), "wheel has no RECORD"
    assert not any(n.startswith("tests/") for n in names), "the wheel must not ship the test suite"
    assert not any(n.startswith("docs/") for n in names), "the wheel must not ship the audit corpus"
    assert copied, "no tracked files were copied — the release population was empty"

    with tempfile.TemporaryDirectory(prefix="drillmaster-installed-target-") as tmp:
        target = Path(tmp) / "site"
        install = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--no-deps", "--no-index",
             "--target", str(target), str(wheel)],
            capture_output=True, text=True)
        assert install.returncode == 0, f"wheel install failed:\n{install.stdout[-1500:]}"

        # Run from a directory that is not the checkout, with the checkout off sys.path.
        run_dir = Path(tmp) / "run"
        run_dir.mkdir()
        probe = (
            "import json, sys\n"
            "import app as app_module\n"
            f"target = {str(target)!r}\n"
            "assert app_module.__file__.startswith(target), app_module.__file__\n"
            "assert not any('Drill-master' in p for p in sys.path), sys.path\n"
            "sys.argv = ['drillmaster', '--package-smoke']\n"
            "code = app_module.main()\n"
            "print(json.dumps({'app': app_module.__file__, 'exit': code}))\n"
        )
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(run_dir),
            "PYTHONPATH": str(target),
            "PYTHONDONTWRITEBYTECODE": "1",
            "LD_LIBRARY_PATH": os.environ.get("LD_LIBRARY_PATH", ""),
            "QT_QPA_PLATFORM": os.environ.get("QT_QPA_PLATFORM", "offscreen"),
            "DRILLMASTER_AI_IMPORT": "0",
        }
        proc = subprocess.run([sys.executable, "-c", probe], cwd=run_dir, env=env,
                              capture_output=True, text=True, timeout=600)
        assert proc.returncode == 0, (
            "the installed artifact could not start its own package smoke from outside the "
            f"checkout (exit {proc.returncode}):\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}")
        assert '"exit": 0' in proc.stdout, proc.stdout[-1000:]


def test_release_population_has_no_cache_or_evidence_artifacts(built_wheel):
    """Release hygiene: the built wheel carries code and declared data, nothing else."""
    wheel, _ = built_wheel
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    forbidden = [n for n in names
                 if "__pycache__" in n or n.endswith((".pyc", ".pyo", ".orig", ".rej", ".bak"))
                 or "docs/audits" in n]
    assert not forbidden, f"cache/scratch/audit artifacts in the wheel: {forbidden[:10]}"
    assert (sysconfig.get_path("purelib") is not None)  # sanity: the interpreter reports paths
