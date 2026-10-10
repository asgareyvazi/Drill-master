"""Guard the Windows release gate's own contract (M42.1).

Two real Windows regressions motivated this file: a test read repository source
with the platform default encoding (cp1252 on the runner) and crashed with
``UnicodeDecodeError``, and per-failure annotations were silently truncated at
GitHub's ten-annotations-per-step limit.  Both are properties of the gate itself,
so they are asserted here rather than discovered by a red CI run.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "windows-release-gate.yml"
REQUIRED_MODULES = (
    "tests/test_packaging_smoke.py",
    "tests/test_acceptance_report.py",
    "tests/test_release_smoke.py",
    "tests/test_credential_lifecycle.py",
    "tests/test_wellbore_schema_v3.py",
    "tests/test_wellbore_ownership_integrity.py",
    "tests/test_wellbore_discriminator_import.py",
    "tests/test_wellbore_identity_conflict_m25.py",
    "tests/test_p0_well_identity.py",
    "tests/test_history_well_scope.py",
    "tests/test_whole_well_scope_labels_m25.py",
    "tests/test_release_gate_and_w13.py",
    "tests/test_w13_ecd_chart_fallback.py",
    "tests/test_w13_fishing_result_ui.py",
    "tests/test_m38_domain_boundaries.py",
    "tests/test_m31_scenarios.py",
    "tests/test_well_centric_acceptance.py",
    "tests/test_production_import_guarantees.py",
    "tests/test_ddr_forensic_regressions.py",
    "tests/test_ddr_followup_lifecycle.py",
    "tests/test_database_migration_acceptance.py",
    "tests/test_backup_restore_acceptance.py",
    "tests/test_import_atomicity_acceptance.py",
    "tests/test_release_e2e.py",
    "tests/test_junit_report.py",
    "tests/test_windows_release_gate_contract.py",
)
ROOT_MARKERS = ("ROOT", "REPO", "parents[1]", "parent.parent", "Path(__file__)")


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _pytest_files(workflow_text: str) -> list[str]:
    match = re.search(r"python -m pytest[^\n]*?(?=--junitxml)", workflow_text)
    assert match, "Windows workflow must invoke pytest with a --junitxml report"
    return sorted({token for token in match.group(0).split() if re.fullmatch(r"tests/test_[a-z0-9_]+\.py", token)})


def test_windows_gate_runs_every_required_release_module(workflow_text):
    listed = _pytest_files(workflow_text)
    missing = [module for module in REQUIRED_MODULES if module not in listed]
    assert not missing, f"Windows regression suite is missing modules: {missing}"


def test_windows_gate_only_references_existing_test_files(workflow_text):
    listed = _pytest_files(workflow_text)
    assert listed, "the Windows pytest invocation must list test modules"
    absent = [module for module in listed if not (ROOT / module).is_file()]
    assert not absent, f"Windows workflow references non-existent test files: {absent}"


def test_windows_suite_reads_repository_text_with_an_explicit_encoding(workflow_text):
    offenders = []
    for module in _pytest_files(workflow_text):
        tree = ast.parse((ROOT / module).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr not in {"read_text", "read", "write_text", "write"}:
                continue
            if node.func.attr == "read" and not node.args:
                continue
            if any(keyword.arg == "encoding" for keyword in node.keywords):
                continue
            if node.func.attr == "read_text" and len(node.args) >= 1:
                continue
            receiver = ast.unparse(node.func.value)
            if any(marker in receiver for marker in ROOT_MARKERS):
                offenders.append(f"{module}:{node.lineno}: {ast.unparse(node)[:90]}")
    assert not offenders, (
        "Windows-suite tests must pass encoding='utf-8' when reading repository source; "
        f"the runner's default encoding is cp1252:\n{chr(10).join(offenders)}"
    )


RELEASE_TOOLS = (
    "verify_release.py",
    "packaging/junit_report.py",
    "packaging/acceptance_report.py",
    "packaging/release_metadata.py",
    "packaging/package_smoke.py",
)


def _unencoded_text_io(module: str) -> list[str]:
    tree = ast.parse((ROOT / module).read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        attribute = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else "")
        if attribute in {"read_text", "write_text", "write_lines"}:
            encoded = any(kw.arg == "encoding" for kw in node.keywords) or bool(node.args)
            if not encoded:
                offenders.append(f"{module}:{node.lineno}: {attribute}() without encoding")
        elif attribute == "open":
            # ``open(path, mode)`` takes the mode second; ``path.open(mode)`` takes it first.
            position = 1 if isinstance(func, ast.Name) else 0
            if len(node.args) > position and isinstance(node.args[position], ast.Constant):
                mode = node.args[position].value
            else:
                mode = next((kw.value.value for kw in node.keywords if kw.arg == "mode" and isinstance(kw.value, ast.Constant)), "")
            binary = "b" in str(mode)
            if not binary and not any(kw.arg == "encoding" for kw in node.keywords):
                offenders.append(f"{module}:{node.lineno}: text-mode open() without encoding")
    return offenders


def test_release_tools_declare_text_encodings():
    """The release tooling itself runs on Windows in the dedicated gate."""
    offenders = [item for module in RELEASE_TOOLS for item in _unencoded_text_io(module)]
    assert not offenders, "release tooling must state text encodings; cp1252 is the Windows default:\n" + "\n".join(offenders)


def test_windows_gate_reports_all_failures_beyond_the_annotation_limit(workflow_text):
    assert "packaging\\junit_report.py" in workflow_text
    assert "GITHUB_STEP_SUMMARY" in workflow_text
    assert "--summary-out" in workflow_text
    assert "::error file=" not in workflow_text, "annotation formatting belongs to the tested parser, not inline PowerShell"


def test_windows_gate_preserves_the_pytest_exit_code(workflow_text):
    block = workflow_text[workflow_text.index("python -m pytest"):]
    block = block[: block.index("- name: Build portable bundle")]
    assert "$pytestExit = $LASTEXITCODE" in block
    assert block.index("if ($pytestExit -ne 0)") > block.index("junit_report.py"), (
        "diagnostics must be emitted before the suite result is propagated"
    )
    assert "Windows release regression suite failed" in block
    assert "if ($pytestExit -eq 0)" not in block, "a passing suite must not be re-derived from report contents"


def test_windows_gate_keeps_the_inno_setup_and_isolation_pins(workflow_text):
    assert "innosetup --version=6.7.1" in workflow_text
    for variable in ("DRILLMASTER_ENV", "DRILLMASTER_DATA_DIR", "DRILLMASTER_DB_PATH", "DRILLMASTER_LOG_DIR", "DRILLMASTER_BACKUP_DIR"):
        assert f"$env:{variable}" in workflow_text, f"{variable} must be isolated to the runner temp root"
    assert "RUNNER_TEMP" in workflow_text
    assert "drillmaster.db" not in workflow_text, "the gate must never point at the default operator database"


# --- the packaging step must be diagnosable on a runner with no reachable log ----

def _build_step(workflow_text: str) -> str:
    start = workflow_text.index("- name: Build portable bundle")
    end = workflow_text.index("- name: Upload Windows evidence artifacts")
    return workflow_text[start:end]


@pytest.fixture(scope="module")
def build_script_text() -> str:
    path = ROOT / "packaging" / "build_windows.ps1"
    return path.read_text(encoding="utf-8")


def test_release_dir_output_precedes_the_build_so_failure_logs_are_uploaded(workflow_text):
    """The evidence upload runs on always(); an output set only on success uploads nothing."""
    block = _build_step(workflow_text)
    publication = block.index('"release_dir=$releaseRoot" | Add-Content $env:GITHUB_OUTPUT')
    assert publication < block.index("& .\\packaging\\build_windows.ps1"), "publish the release directory before the build can fail"
    assert block.count('"release_dir=$releaseRoot"') == 1


def test_build_stage_failure_is_published_as_an_annotation(workflow_text):
    """A red step whose reason lives only in an unreachable log is not triageable."""
    block = _build_step(workflow_text)
    assert "} catch {" in block and "throw" in block.split("} catch {")[1], "the catch must re-raise so the step stays red"
    assert "junit_report.py --annotate" in block
    assert "--annotate-message" in block and "--annotate-file" in block
    assert "Start-Transcript" in block and "Stop-Transcript" in block
    assert "$transcriptStarted" in block, "a failing transcript setup must not become the build failure"
    assert "DrillMaster-build-transcript-" in workflow_text.split("- name: Upload Windows evidence artifacts")[1], (
        "the captured transcript must be uploaded with the rest of the release evidence")


def test_build_step_treats_a_thrown_stage_failure_as_fatal(workflow_text):
    """Without Stop, an error thrown by the called script would be printed and execution would continue."""
    block = _build_step(workflow_text)
    assert "$ErrorActionPreference = 'Stop'" in block
    assert block.index("$ErrorActionPreference = 'Stop'") < block.index("& .\\packaging\\build_windows.ps1")


def test_gate_builds_with_the_interpreter_it_provisioned(workflow_text, build_script_text):
    """The py launcher resolves registry-registered runtimes, not the Actions tool cache."""
    block = _build_step(workflow_text)
    assert "(Get-Command python).Source" in block
    assert "-PythonExe $pythonExe" in block
    assert "-PythonLauncher" not in block, "CI must not select the interpreter through the py launcher"
    assert "[string]$PythonExe" in build_script_text


def test_build_script_validates_the_interpreter_and_survives_stderr_logging(build_script_text):
    assert "-notmatch \"^$([regex]::Escape($PythonVersion))\\.\"" in build_script_text, (
        "an explicit -PythonExe must still satisfy the required minor version")
    assert "$PSNativeCommandUseErrorActionPreference = $false" in build_script_text, (
        "PyInstaller logs to stderr; PowerShell 7.3+ would treat it as a terminating error")
    piped = build_script_text.index("2>&1 | Tee-Object")
    window = build_script_text[piped - 500:piped + 500]
    assert '$ErrorActionPreference = "Continue"' in window and "$preferenceBeforePyInstaller = $ErrorActionPreference" in window, (
        "the redirected pipeline must not run under Stop, which turns stderr into a fatal NativeCommandError")
    assert "$pyinstallerExit = $LASTEXITCODE" in build_script_text[piped:piped + 400], (
        "a redirected native command must have its exit code captured before any other statement")


CHECKPOINT = ROOT / "docs" / "audits" / "m42-1-release-closure.json"

def test_checkpoint_records_the_packaging_stage_without_inventing_a_root_cause():
    """The instrumented gate, not the checkpoint, is what names the failing stage."""
    payload = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    record = payload["packaging_stage_forensics"]
    assert record["root_cause_category"] in {
        "PRODUCT_DEFECT", "WINDOWS_PORTABILITY_DEFECT", "CI_HARNESS_DEFECT",
        "ENVIRONMENTAL_LIMITATION", "UNRESOLVED",
    }
    assert record["failing_stage_at_first_run"] == "UNRESOLVED_PENDING_INSTRUMENTED_RUN"
    assert record["product_code_affected"] is False
    assert record["credential_security_invariants_changed"] is False
    assert re.fullmatch(r"[0-9a-f]{40}", record["sha"])
    for node_id in record["regression_test"]:
        relative, _, test_name = node_id.partition("::")
        assert (ROOT / relative).is_file(), relative
        assert f"def {test_name}(" in (ROOT / relative).read_text(encoding="utf-8"), node_id



def test_m42_1_checkpoint_records_boundaries_without_claiming_ci_results():
    """A committed checkpoint must not assert the outcome of the run that validates it."""
    assert CHECKPOINT.is_file()
    payload = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    assert payload["mission"] == "M42.1"
    assert payload["branch"] == "arena/01a0ec23-drill-master"
    assert payload["credential_failure_forensics"]["classification"] == "WINDOWS_PORTABILITY_DEFECT"
    assert payload["credential_failure_forensics"]["credential_security_invariants_changed"] is False
    assert payload["credential_failure_forensics"]["product_code_affected"] is False
    gates = {item["gate"]: item["workflow_file"] for item in payload["internal_gates"]}
    assert set(gates) == {"source_release_gate", "windows_release_validation"}
    for relative in gates.values():
        assert (ROOT / relative).is_file(), relative
    assert all(value == "NOT_RUN" for key, value in payload["external_acceptance"].items()
               if key != "synthetic_workbook_scenario")
    assert payload["external_acceptance"]["synthetic_workbook_scenario"] == "AUTOMATED_TEST_ONLY_NOT_REAL_DDR_ACCEPTANCE"
    committed = CHECKPOINT.read_text(encoding="utf-8")
    assert "actions/runs/" not in committed, "run evidence is published by CI, never committed"
    assert re.search(r'"run_id"\s*:\s*"\d+"', committed) is None
    assert re.search(r"\b\d{10,}\b", committed) is None, (
        "a workflow run number is 10+ digits; the checkpoint must reference the SHA and let CI carry the run identity")
    for relative in payload["credential_failure_forensics"]["regression_guard"]:
        assert (ROOT / relative).is_file(), relative
    assert (ROOT / payload["runbook"]).is_file()
    assert "m42-1-release-closure.json" in (ROOT / "PRODUCTION_READINESS.md").read_text(encoding="utf-8")
