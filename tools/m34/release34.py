#!/usr/bin/env python3
"""M34 Parts Q/R/S: clean-environment lock check, wheel build/install/run, Commit-1 simulation.

Stage ``wheel``   — requirements-lock installation in a throwaway venv, then a wheel built from
                    *tracked files only* (the same population the release gate can see), installed
                    into that clean venv and imported from outside the checkout.
Stage ``commit1`` — overlay of HEAD + the proposed Commit-1 file set in a temp tree, then compile,
                    collect, targeted behaviour and (optionally) the full suite *without* any audit
                    record present, proving Commit 1 stands alone.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / "docs" / "audits" / "m34-evidence"
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")
PY_SYS = "/usr/bin/python3"
BUILD_PY = "/home/user/verify-venv/bin/python"
TEST_ENV = dict(os.environ)
TEST_ENV.update({"PYTHONDONTWRITEBYTECODE": "1", "LD_LIBRARY_PATH": "/tmp/qtstub",
                 "QT_QPA_PLATFORM": "offscreen", "DRILLMASTER_AI_IMPORT": "0"})

PACKAGING = ["pyproject.toml", "requirements.txt", "requirements-lock.txt", "requirements-build.txt",
             "requirements-optional.txt", "pytest.ini", "setup.py", "setup.cfg", "MANIFEST.in",
             ".gitignore", "README.md", "LICENSE"]


def run(cmd, cwd=ROOT, env=None, timeout=1200, binary=False):
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env or TEST_ENV, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"cmd": cmd, "exit_code": None, "outcome": "TIMEOUT", "seconds": round(time.time() - t0, 1),
                "stdout": "", "stderr": ""}
    out = p.stdout.decode("utf-8", "replace") if binary else p.stdout.decode("utf-8", "replace")
    err = p.stderr.decode("utf-8", "replace")
    return {"cmd": cmd, "exit_code": p.returncode, "outcome": "OK" if p.returncode == 0 else "FAIL",
            "seconds": round(time.time() - t0, 1), "stdout": out[-4000:], "stderr": err[-2000:]}


def tracked_files() -> list[str]:
    return [n for n in subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                                      capture_output=True).stdout.decode().split("\0") if n]


def stage_wheel() -> dict:
    lock = ROOT / "requirements-lock.txt"
    lock_pins = [ln.strip() for ln in lock.read_text().splitlines()
                 if ln.strip() and not ln.strip().startswith("#")]
    venv = Path("/tmp/m34-clean-venv")
    if venv.exists():
        shutil.rmtree(venv)
    created = run([PY_SYS, "-m", "venv", str(venv)], timeout=300)
    pip = venv / "bin" / "pip"
    installed = run([str(pip), "install", "--quiet", "-r", str(lock)], timeout=1800)
    pip_check = run([str(pip), "check"], timeout=300)
    freeze = run([str(pip), "freeze"], timeout=300)
    freeze_lines = [ln for ln in freeze["stdout"].splitlines() if ln.strip()]

    def canon(spec: str) -> tuple[str, str]:
        spec = re.split(r";|\[", spec)[0].strip()
        parts = re.split(r"==|>=|<=|~=|>|<", spec, maxsplit=1)
        name = parts[0].strip().lower().replace("_", "-")
        version = parts[1].strip() if len(parts) > 1 else ""
        return name, version

    want = dict(canon(p) for p in lock_pins)
    got = dict(canon(f) for f in freeze_lines)
    exact = {n: v for n, v in want.items() if got.get(n) == v}
    mismatched = {n: {"lock": v, "installed": got.get(n)} for n, v in want.items() if got.get(n) != v}

    # wheel from tracked files only
    wheel_report = {}
    with tempfile.TemporaryDirectory(prefix="m34-wheel-") as tmp:
        tmpd = Path(tmp)
        source = tmpd / "source"
        source.mkdir()
        missing = 0
        for name in tracked_files():
            src = ROOT / name
            if not src.is_file():
                continue
            dst = source / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(src, dst)
            except OSError:
                missing += 1
        # the repository's own gate builds with isolation (verify_release.verify_wheel), so the
        # pinned build toolchain is fetched rather than assumed present in the checker's venv
        build = run([BUILD_PY, "-m", "build", "--wheel", "--outdir", str(tmpd / "dist")],
                    cwd=source, timeout=1800)
        wheels = sorted((tmpd / "dist").glob("*.whl")) if (tmpd / "dist").exists() else []
        wheel_report = {"tracked_file_population": len(tracked_files()), "copied": sum(
            1 for _ in source.rglob("*") if _.is_file()), "copy_failures": missing,
            "build": {k: build[k] for k in ("exit_code", "outcome", "seconds")},
            "build_tail": build["stdout"][-700:] if build["exit_code"] else ""}
        if wheels:
            wheel = wheels[0]
            wheel_report["wheel"] = {"name": wheel.name, "bytes": wheel.stat().st_size,
                                     "sha256": __import__("hashlib").sha256(wheel.read_bytes()).hexdigest()}
            with zipfile.ZipFile(wheel) as zf:
                names = zf.namelist()
            top = sorted({n.split("/")[0] + "/" + n.split("/")[1] for n in names
                          if n.startswith(("core/", "tabs/", "dialogs/")) and n.endswith(".py")})
            absent = [m for m in ("core/operational_time.py", "core/safety_semantics.py")
                      if m not in names]
            wheel_report["packaged_modules_sampled"] = len(top)
            wheel_report["modules_absent_from_wheel"] = absent
            required = ["app.py", "main_window.py", "core/database.py", "ui/helper.py", "ui/utils.py",
                        "config/ai_models.json", "config/company_templates/oeoc.json",
                        "templates/OEOC_DDR_v3.json"]
            wheel_report["required_entries_present"] = {name: name in names for name in required}
            wheel_report["tests_shipped_in_wheel"] = any(n.startswith("tests/") for n in names)
            installed_dir = tmpd / "installed"
            install = run([str(pip), "install", "--quiet", "--no-deps", "--no-index",
                           "--target", str(installed_dir), str(wheel)], timeout=600)
            wheel_report["install_into_clean_venv"] = {k: install[k] for k in ("exit_code", "outcome")}
            package_smoke = run([str(venv / "bin" / "python"), str(installed_dir / "app.py"), "--package-smoke"],
                                cwd="/tmp", timeout=600)
            wheel_report["app_package_smoke_outside_checkout"] = {
                "exit_code": package_smoke["exit_code"], "outcome": package_smoke["outcome"],
                "stdout": package_smoke["stdout"][-1200:], "stderr": package_smoke["stderr"][-600:]}
            probe = (
                "import sys, traceback\n"
                "results = {}\n"
                "for mod in ('core.report_engine', 'core.ddr_pdf_export', 'core.operations_intelligence',\n"
                "            'core.actual_vs_plan', 'tabs.w10_Planning_Widget'):\n"
                "    try:\n"
                "        __import__(mod); results[mod] = 'IMPORT-OK'\n"
                "    except Exception as exc:\n"
                "        results[mod] = f'{type(exc).__name__}: {exc}'\n"
                "import core.engineering.engines.casing as casing\n"
                "from core.engineering.engines.casing import CasingEngine\n"
                "try:\n"
                "    r = CasingEngine.evaluate(od_in=9.625, weight_ppf=47.0, grade='N80', wall_thickness_in=0.472)\n"
                "    results['casing_evaluate'] = 'SUCCESS' if r.success else f'ENGINE-FAILED: {r.error}'\n"
                "except Exception as exc:\n"
                "    results['casing_evaluate'] = f'{type(exc).__name__}: {exc}'\n"
                "print(__import__('json').dumps(results, indent=1))\n"
                "print('PACKAGE_DIR', casing.__file__)\n")
            probe_path = tmpd / "probe.py"
            probe_path.write_text(probe)
            smoke = run([str(venv / "bin" / "python"), str(probe_path)], cwd="/tmp", timeout=600)
            wheel_report["smoke_from_outside_checkout"] = {
                "exit_code": smoke["exit_code"], "outcome": smoke["outcome"],
                "stdout": smoke["stdout"][-2000:], "stderr": smoke["stderr"][-800:]}
    return {
        "schema": "m34-clean-env-and-wheel",
        "generated_utc": NOW,
        "lock": {"path": "requirements-lock.txt", "pins": len(lock_pins),
                 "installed_exactly": len(exact), "mismatched": mismatched,
                 "pip_check": pip_check["outcome"], "pip_check_output": pip_check["stdout"][-300:],
                 "venv": str(venv), "created": created["outcome"]},
        "wheel": wheel_report,
        "verdicts": {
            "lock_exact": len(mismatched) == 0 and pip_check["outcome"] == "OK",
            "wheel_builds_from_tracked_files": wheel_report.get("build", {}).get("exit_code") == 0,
            "wheel_contains_required_entries": all(
                wheel_report.get("required_entries_present", {}).values()) if wheel_report.get(
                "required_entries_present") else None,
            "wheel_excludes_tests": wheel_report.get("tests_shipped_in_wheel") is False,
            "wheel_entrypoint_runs_outside_checkout":
                wheel_report.get("app_package_smoke_outside_checkout", {}).get("exit_code") == 0,
            "wheel_blocking_evidence": (wheel_report.get("app_package_smoke_outside_checkout", {})
                                        .get("stderr", "") or "")[-400:],
            "modules_absent_from_tracked_wheel": wheel_report.get("modules_absent_from_wheel"),
        },
        "truth_note": "the wheel is built from the tracked population only, which is exactly what a "
                      "release artefact can contain; if a module that production code imports is not "
                      "tracked, the wheel probe reports ModuleNotFoundError and that is recorded as a "
                      "repository blocker rather than explained away",
    }


def commit1_file_set() -> tuple[list[str], list[dict]]:
    status = subprocess.run(["git", "status", "--porcelain", "-z", "-uall"], cwd=ROOT,
                            capture_output=True).stdout.decode("utf-8", "replace")
    toks = [t for t in status.split("\0") if t]
    picked, decisions = [], []
    for tok in toks:
        code, path = tok[:2], tok[3:]
        if path.startswith(("docs/audits/", "tools/")) or path.endswith(".md"):
            why = "audit record / report / analysis tooling → Commit 2"
            cls = "COMMIT-2"
        elif path.startswith((".github/", "requirements", "packaging/")) or path in PACKAGING \
                or path.endswith((".spec", ".ps1", ".bat", ".iss", ".nsi")):
            why, cls = "packaging, configuration or CI", "COMMIT-1"
        elif path.startswith("tests/"):
            why, cls = "test", "COMMIT-1"
        elif re.match(r"^(core|tabs|dialogs|config|ui|templates|assets)/", path) or path.endswith(".py"):
            why, cls = "production code", "COMMIT-1"
        else:
            why, cls = "not classified as code/test/config — needs a human decision", "REVIEW-REQUIRED"
        decisions.append({"path": path, "status": code.strip() or "??", "class": cls, "why": why})
        if cls == "COMMIT-1":
            picked.append(path)
    for extra in ("core/operational_time.py", "core/safety_semantics.py"):
        if extra not in picked and (ROOT / extra).exists():
            picked.append(extra)
            decisions.append({"path": extra, "status": "??", "class": "COMMIT-1",
                              "why": "imported by tracked production modules; the tracked-only wheel "
                                     "probe shows it must ship in Commit 1"})
    return sorted(set(picked)), decisions


def stage_commit1(run_full_suite: bool) -> dict:
    picked, decisions = commit1_file_set()
    with tempfile.TemporaryDirectory(prefix="m34-commit1-") as tmp:
        tree = Path(tmp) / "tree"
        tree.mkdir()
        arch = subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, capture_output=True)
        tar = subprocess.run(["tar", "-x", "-C", str(tree)], input=arch.stdout, capture_output=True)
        for rel in picked:
            src, dst = ROOT / rel, tree / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        env = dict(TEST_ENV)
        env["PYTHONPATH"] = str(tree)
        compile_out = run([PY_SYS, "-m", "compileall", "-q", "core", "tabs", "dialogs", "tests"],
                          cwd=tree, timeout=900)
        collect = run(["/home/user/verify-venv/bin/python", "-m", "pytest", "--collect-only", "-q",
                       "-p", "no:cacheprovider"], cwd=tree, timeout=900)
        collected = sum(int(m) for m in re.findall(r": (\d+)$", collect["stdout"], re.M))
        targeted = run(["/home/user/verify-venv/bin/python", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        "-W", "ignore::DeprecationWarning",
                        "tests/test_casing_absent_load_semantics.py",
                        "tests/test_m31_scenarios.py",
                        "tests/test_report_scoped_ownership_m26.py",
                        "tests/test_autosave_manager_regression.py"], cwd=tree, timeout=1800)
        full = None
        if run_full_suite:
            full = run(["/home/user/verify-venv/bin/python", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        "-W", "ignore::DeprecationWarning", "-ra",
                        f"--junitxml={EV / 'm34-commit1-overlay-junit.xml'}"], cwd=tree, timeout=1800)
        missing_in_overlay = [m for m in ("core/operational_time.py", "core/safety_semantics.py")
                              if not (tree / m).exists()]
        import_probe = (
            "import json, sys\n"
            "res = {}\n"
            "for mod in ('core.report_engine', 'core.ddr_pdf_export', 'core.operations_intelligence',\n"
            "            'core.actual_vs_plan', 'tabs.w10_Planning_Widget'):\n"
            "    try:\n"
            "        __import__(mod); res[mod] = 'IMPORT-OK'\n"
            "    except Exception as exc:\n"
            "        res[mod] = f'{type(exc).__name__}: {exc}'\n"
            "from core.engineering.engines.casing import CasingEngine\n"
            "r = CasingEngine.evaluate(od_in=9.625, wall_in=0.472, id_in=8.681, yield_psi=80000.0)\n"
            "res['casing_evaluate'] = 'SUCCESS' if r.success else f'FAILED: {r.error}'\n"
            "print(json.dumps(res, indent=1))\n")
        (tree / "_m34_probe.py").write_text(import_probe)
        overlay_smoke = run(["/home/user/verify-venv/bin/python", "_m34_probe.py"], cwd=tree, timeout=600)
        (tree / "_m34_probe.py").unlink()
        # dependency check: no Commit-1 file may reference an audit record or a tool
        refs, imports, citations = [], [], []
        for rel in picked:
            if not rel.endswith(".py"):
                continue
            text = (tree / rel).read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r"(?:^|\n)\s*(?:from|import)\s+(docs|tools)\b", text):
                imports.append({"path": rel, "reference": m.group(0).strip()[:60]})
            for m in re.finditer(r"docs/audits/[\w./-]+", text):
                citations.append({"path": rel, "reference": m.group(0)[:70]})
        return {
            "schema": "m34-commit1-simulation",
            "generated_utc": NOW,
            "method": "git archive HEAD (tracked pre-image) + the Commit-1 file set copied over it, "
                      "with no audit record, report or tool from this mission present",
            "commit1_files": len(picked), "commit1_paths": picked,
            "decisions": decisions,
            "compileall": {k: compile_out[k] for k in ("exit_code", "outcome")},
            "collect_only": {"exit_code": collect["exit_code"], "collected": collected,
                             "tail": collect["stdout"][-300:]},
            "targeted_tests": {k: targeted[k] for k in ("exit_code", "outcome", "seconds")},
            "targeted_tail": targeted["stdout"][-500:],
            "full_suite_in_overlay": None if full is None else {
                k: full[k] for k in ("exit_code", "outcome", "seconds")},
            "full_suite_tail": "" if full is None else full["stdout"][-600:],
            "previously_untracked_modules_present_in_overlay": not missing_in_overlay,
            "missing_in_overlay": missing_in_overlay,
            "import_smoke": {"exit_code": overlay_smoke["exit_code"], "outcome": overlay_smoke["outcome"],
                             "stdout": overlay_smoke["stdout"][-1200:], "stderr": overlay_smoke["stderr"][-500:]},
            "audit_or_tooling_imports_in_commit1_code": imports,
            "documentation_citations_in_commit1_code": citations,
            "audit_or_tooling_references_in_commit1_code": refs,
            "self_contained": compile_out["exit_code"] == 0 and collect["exit_code"] == 0
                              and targeted["exit_code"] == 0 and not imports
                              and overlay_smoke["exit_code"] == 0 and not missing_in_overlay
                              and (full is None or full["exit_code"] == 0),
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["wheel", "commit1"], required=True)
    ap.add_argument("--full-suite", action="store_true")
    args = ap.parse_args()
    if args.stage == "wheel":
        payload = stage_wheel()
        out = EV / "m34-wheel-and-clean-env.json"
    else:
        payload = stage_commit1(args.full_suite)
        out = EV / "m34-commit-staging-simulation.json"
    out.write_text(json.dumps(payload, indent=1))
    print(json.dumps({k: v for k, v in payload.items()
                      if k in ("verdicts", "lock", "self_contained", "commit1_files")}, indent=1)[:2500])
    print("written", out.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
