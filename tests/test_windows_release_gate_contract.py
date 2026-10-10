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


CHECKPOINT = ROOT / "docs" / "audits" / "m42-1-release-closure.json"


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
    for relative in payload["credential_failure_forensics"]["regression_guard"]:
        assert (ROOT / relative).is_file(), relative
    assert (ROOT / payload["runbook"]).is_file()
    assert "m42-1-release-closure.json" in (ROOT / "PRODUCTION_READINESS.md").read_text(encoding="utf-8")
