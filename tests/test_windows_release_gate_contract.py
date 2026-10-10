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
    "tests/test_windows_release_evidence.py",
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
    "packaging/windows_release_evidence.py",
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


def test_signing_vocabulary_and_extraction_rules_are_declared_exactly_once():
    """Two definitions of one vocabulary is how a gate starts disagreeing with itself."""
    packaging = Path(__file__).resolve().parents[1] / "packaging"
    sources = {path.name: ast.parse(path.read_text(encoding="utf-8"))
               for path in (packaging / "release_metadata.py", packaging / "acceptance_report.py",
                            packaging / "windows_release_evidence.py")}
    owners = []
    for name, tree in sources.items():
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if any(isinstance(target, ast.Name) and target.id == "SIGNING_STATUS_VOCABULARY"
                       for target in targets):
                    owners.append(name)
    assert owners == ["release_metadata.py"], f"vocabulary defined in {owners}"
    for name in ("acceptance_report.py", "windows_release_evidence.py"):
        imported = {alias.name for node in ast.walk(sources[name]) if isinstance(node, ast.ImportFrom)
                    and node.module == "release_metadata" for alias in node.names}
        assert "SIGNING_STATUS_VOCABULARY" in imported, f"{name} must import the shared vocabulary"
    # the inner executable is only ever obtained through the archive-bound extraction helper
    evidence = (packaging / "windows_release_evidence.py").read_text(encoding="utf-8")
    assert "def extract_verified_member(" in evidence
    assert evidence.count("extract_verified_member(") >= 2
    assert 'release_root / exe_name' not in evidence, (
        "a loose release-directory copy must never stand in for the packaged executable"
    )


def test_runbook_documents_the_archive_bound_signing_and_required_record_contract():
    text = (Path(__file__).resolve().parents[1] / "packaging" / "WINDOWS_RELEASE_ACCEPTANCE.md").read_text(encoding="utf-8")
    for fragment in ("extracted from the portable archive", "container_archive_sha256",
                     "not examined, because nothing binds it", "--require-signing",
                     "Signature record malformed", "PACKAGE_SMOKE_OK"):
        assert fragment in text, f"runbook must document: {fragment}"


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


def test_windows_gate_keeps_the_isolation_pins(workflow_text):
    for variable in ("DRILLMASTER_ENV", "DRILLMASTER_DATA_DIR", "DRILLMASTER_DB_PATH", "DRILLMASTER_LOG_DIR", "DRILLMASTER_BACKUP_DIR"):
        assert f"$env:{variable}" in workflow_text, f"{variable} must be isolated to the runner temp root"
    assert "RUNNER_TEMP" in workflow_text
    assert "drillmaster.db" not in workflow_text, "the gate must never point at the default operator database"


# --- build-lock dependency constraints that only exist under a Windows marker ----

# Edges recorded from PyPI metadata on 2026-10-10 for the pinned versions below.  The
# pefile edge carries sys_platform == "win32", so resolving these files on Linux cannot
# see the conflict at all -- that is how the packaging gate became the first place it
# surfaced, and it is why the constraint is recorded here instead of discovered again.
RECORDED_DEPENDENCY_EDGES = (
    ("pyinstaller==6.11.1", "pefile", ">=2022.5.30,!=2024.8.26"),
    ("PySide6==6.8.1.1", "shiboken6", "==6.8.1.1"),
    ("PySide6==6.8.1.1", "PySide6-Essentials", "==6.8.1.1"),
    ("PySide6==6.8.1.1", "PySide6-Addons", "==6.8.1.1"),
)


def _requirement_pins(path: Path) -> dict[str, str]:
    pins = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, version = line.partition("==")
        assert separator, f"{path.name} must stay fully pinned; unpinned requirement: {line}"
        pins[name.strip().lower().replace("_", "-")] = version.strip()
    assert pins, f"{path.name} parsed to no requirements"
    return pins


def test_release_requirement_files_stay_fully_pinned():
    """An unpinned build or runtime requirement makes the packaged binary unreproducible."""
    assert _requirement_pins(ROOT / "requirements-build.txt")
    assert _requirement_pins(ROOT / "requirements-lock.txt")


# Environment invariants of the build toolchain, recorded from a local before/after
# reproduction instead of PyPI metadata: they are about what the *installed* toolchain can
# import, which no requirement specifier of another package describes.
BUILD_TOOLCHAIN_INVARIANTS = (
    ("altgraph", ">=0.17.5",
     "0.17.4 imports pkg_resources at module scope, which the pinned setuptools no longer provides"),
)


def test_build_toolchain_does_not_depend_on_a_removed_setuptools_module():
    """A build venv must not need a module its own pinned setuptools dropped."""
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version

    pins = _requirement_pins(ROOT / "requirements-build.txt")
    assert "setuptools" in pins, (
        "an unpinned setuptools decided whether the packaged build could start; pin the provider")
    violations = [
        f"{dependency}=={pins[dependency]} violates the recorded invariant {specifier} ({reason})"
        for dependency, specifier, reason in BUILD_TOOLCHAIN_INVARIANTS
        if Version(pins[dependency]) not in SpecifierSet(specifier)
    ]
    assert not violations, "Windows packaging toolchain is unusable:\n" + "\n".join(violations)


def test_windows_build_toolchain_satisfies_its_own_windows_markers():
    from packaging.specifiers import SpecifierSet
    from packaging.version import Version

    pins = {}
    pins.update(_requirement_pins(ROOT / "requirements-lock.txt"))
    pins.update(_requirement_pins(ROOT / "requirements-build.txt"))
    conflicts = []
    for consumer, dependency, specifier in RECORDED_DEPENDENCY_EDGES:
        consumer_name, _, consumer_version = consumer.partition("==")
        assert pins[consumer_name.strip().lower().replace("_", "-")] == consumer_version, (
            f"{consumer} is recorded from PyPI metadata but the repository pins a different "
            f"version; re-record the constraint edges before changing this pin")
        pinned = pins[dependency.strip().lower().replace("_", "-")]
        if Version(pinned) not in SpecifierSet(specifier):
            conflicts.append(f"{dependency}=={pinned} violates {consumer}'s requirement {specifier}")
    assert not conflicts, "Windows packaging environment is unresolvable:\n" + "\n".join(conflicts)


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
    assert block.index("Stop-Transcript") < block.index("--annotate"), (
        "annotating an open transcript publishes only what it has flushed so far")
    for log in ("pip-install.log", "pyinstaller-build.log"):
        assert f"'{log}'" in block, f"{log} must be part of the published diagnostics"
    assert "GITHUB_STEP_SUMMARY" in block.split("} finally {")[1], "the same reason belongs in the job summary"
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


def test_build_script_captures_the_dependency_install_and_checks_output_first(build_script_text):
    """A pip failure must carry its own reason, and the release dir must exist before logs are written."""
    assert 'Join-Path $releaseRoot "pip-install.log"' in build_script_text
    assert "Locked dependency installation failed (exit $pipExit)" in build_script_text
    assert "Dependency consistency check failed (exit $pipCheckExit)" in build_script_text
    assert "$pipTail = @(Get-Content -LiteralPath $dependencyLog -Tail 30)" in build_script_text
    guard = build_script_text.index("Refusing to delete or overwrite existing release output")
    assert guard < build_script_text.index("$buildVenv ="), (
        "the release output guard must precede anything that writes into the release directory")


def test_build_script_validates_the_interpreter_and_survives_stderr_logging(build_script_text):
    assert "-notmatch \"^$([regex]::Escape($PythonVersion))\\.\"" in build_script_text, (
        "an explicit -PythonExe must still satisfy the required minor version")
    assert "$PSNativeCommandUseErrorActionPreference = $false" in build_script_text, (
        "PyInstaller logs to stderr; PowerShell 7.3+ would treat it as a terminating error")
    redirected = [m.start() for m in re.finditer(r"2>&1 \| Tee-Object", build_script_text)]
    assert redirected, "the build script must keep a captured log for each redirected native stage"
    for offset in redirected:
        before = build_script_text[max(0, offset - 700):offset]
        after = build_script_text[offset:offset + 500]
        assert '$ErrorActionPreference = "Continue"' in before, (
            "a redirected pipeline must not run under Stop, which turns native stderr into a fatal NativeCommandError")
        following = "\n".join(after.splitlines()[1:3])
        assert "$LASTEXITCODE" in following, (
            "a redirected native command must capture its exit code before any other statement")


CHECKPOINT = ROOT / "docs" / "audits" / "m42-1-release-closure.json"

def test_checkpoint_records_the_build_toolchain_defect_with_its_reproduction():
    """A root cause claimed as found must name a reproduction, not only a conclusion."""
    payload = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    record = payload["pyinstaller_stage_forensics"]
    assert record["root_cause_category"] in {
        "PRODUCT_DEFECT", "WINDOWS_PORTABILITY_DEFECT", "CI_HARNESS_DEFECT",
        "ENVIRONMENTAL_LIMITATION", "UNRESOLVED",
    }
    assert record["exception"] == "ModuleNotFoundError: No module named 'pkg_resources'"
    assert "reproduc" in record["reproduction"].lower() and "altgraph" in record["reproduction"]
    assert record["verification"] == "SEPARATE_EXACT_SHA_WORKFLOW_REQUIRED"
    assert record["product_runtime_affected"] is False
    for node_id in record["regression_test"]:
        relative, _, test_name = node_id.partition("::")
        assert f"def {test_name}(" in (ROOT / relative).read_text(encoding="utf-8"), node_id


def test_checkpoint_records_the_packaging_stage_without_inventing_a_root_cause():
    """The instrumented gate, not the checkpoint, is what names the failing stage."""
    payload = json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    record = payload["packaging_stage_forensics"]
    assert record["root_cause_category"] in {
        "PRODUCT_DEFECT", "WINDOWS_PORTABILITY_DEFECT", "CI_HARNESS_DEFECT",
        "ENVIRONMENTAL_LIMITATION", "UNRESOLVED",
    }
    assert record["failing_stage"], "the annotated stage must be recorded"
    mechanism = record.get("stage_mechanism", "UNRESOLVED_PENDING_CAPTURED_PIP_LOG")
    if mechanism.startswith("UNRESOLVED"):
        assert record["resolution_verification"] == "SEPARATE_EXACT_SHA_WORKFLOW_REQUIRED", (
            "an unproven mechanism must be marked unresolved, never asserted as fixed")
    else:
        assert record["resolution_verification"] == "SEPARATE_EXACT_SHA_WORKFLOW_REQUIRED", (
            "even a proven mechanism is only verified by the exact-SHA gate")
    for correction in record.get("corrections", []):
        assert all(correction[key].strip() for key in ("superseded_claim", "why_wrong", "corrected_method"))
    assert "actions/runs/" not in json.dumps(record)
    assert re.fullmatch(r"[0-9a-f]{40}", record["stage_identified_at_sha"])
    for ruled in record["ruled_out"]:
        assert ruled["hypothesis"].strip() and ruled["evidence"].strip(), ruled
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


# --- M42.2: toolchain identity must be established, not assumed ----------------

PIN_FILE = ROOT / "packaging" / "inno_setup_version.txt"
BUILD_SCRIPT = ROOT / "packaging" / "build_windows.ps1"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load(module_path: Path, name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_innosetup_version_has_a_single_pinned_source_of_truth(workflow_text):
    """The request, the read-back and the published manifest must share one value."""
    pin = _read(PIN_FILE).strip()
    assert re.fullmatch(r"\d+\.\d+\.\d+", pin), f"the pin must be an exact version, got {pin!r}"
    assert "packaging\\inno_setup_version.txt" in workflow_text
    assert "choco install innosetup --version=$innoPin" in workflow_text
    # A second copy of the number could drift, so the workflow must not carry one.
    assert pin not in workflow_text.replace("$innoPin", ""), (
        "the Windows workflow must read the Inno Setup version from the pin file, not repeat it"
    )
    build_text = _read(BUILD_SCRIPT)
    assert 'Get-Content -LiteralPath $innoPinFile' in build_text
    assert "inno_setup_version.txt" in build_text
    assert "6.7.1" not in build_text, "the build script must not hardcode a version literal"


def test_innosetup_identity_is_read_back_and_fail_closed(workflow_text):
    """Requesting a version is not the same as proving it; both halves must be present."""
    install_step = workflow_text.split("Install pinned Inno Setup compiler", 1)[1].split("- name:", 1)[0]
    assert "chocolatey" in install_step and "innosetup.nuspec" in install_step
    assert "$installed -ne $innoPin" in install_step
    assert "could not be established" in install_step
    assert "innosetup_version=$installed" in install_step

    build_text = _read(BUILD_SCRIPT)
    assert "Resolve-InnoSetupIdentity" in build_text
    assert "$PackageName.nuspec" in build_text or "chocolatey\\lib\\$PackageName" in build_text
    assert "installed-package-metadata" in build_text
    assert "operator-attested" in build_text
    assert "Inno Setup identity disagreement" in build_text, "a caller value must cross-check, not replace, the read-back"
    assert "does not satisfy the pinned version" in build_text
    assert "not an exact dotted version" in build_text
    assert "all-zero" in build_text
    # The executable's own resource is retained only as a labelled diagnostic.
    resource_lines = [line for line in build_text.splitlines()
                      if "VersionInfo.FileVersion" in line and not line.strip().startswith("#")]
    assert len(resource_lines) == 1, "the file resource must be read exactly once, as a diagnostic"
    assert "reported" in resource_lines[0]
    assert '"UNAVAILABLE"' in build_text, "an absent file resource is recorded as unavailable, never as a version"
    assert '"--innosetup-version", $innoVersion' not in build_text, (
        "the unverified VersionInfo field must never be published as the toolchain identity"
    )
    assert "$innoPackageVersion = $innoIdentity.PackageVersion" in build_text
    assert "CompilerFileVersion" in build_text
    assert "--innosetup-package-version" in build_text and "--innosetup-file-version" in build_text


def test_release_manifest_schema_and_workflow_check_agree(workflow_text):
    """A manifest published under a different schema must not satisfy the gate."""
    metadata_module = _load(ROOT / "packaging" / "release_metadata.py", "drillmaster_release_metadata_contract")
    assert metadata_module.SCHEMA in workflow_text
    assert "innosetup_identity_verified" in workflow_text
    assert "innosetup_package_version -ne" in workflow_text, (
        "the workflow must compare the published identity against the version it verified"
    )


def _step_block(workflow_text: str, title: str) -> str:
    assert title in workflow_text, f"the Windows workflow lost its {title!r} step"
    block = workflow_text.split(title, 1)[1]
    return block.split("\n      - name:", 1)[0]


def test_installed_lifecycle_step_is_bound_to_the_published_installer(workflow_text):
    block = _step_block(workflow_text, "Installed-application lifecycle smoke")
    assert "if: steps.build.outcome == 'success'" in block, "the lifecycle smoke must only run on a completed build"
    assert "windows_release_evidence.py lifecycle" in block
    assert 'DrillMaster-$version-Setup.exe' in block
    assert "--release-metadata" in block and "--app-version $version" in block
    assert "--json-out" in block and "installer-lifecycle.json" in block
    # isolated, disposable, and cleaned up even when the smoke fails
    assert "RUNNER_TEMP" in block
    assert "} finally {" in block and "Remove-Item" in block
    assert "junit_report.py --annotate" in block, "a failing lifecycle step must publish its reason"
    assert "throw $stageError" in block, "a failing lifecycle step must not leave the job green"
    assert "DRILLMASTER_DB_PATH" not in block, "the lifecycle smoke must never target the default operator database"


def test_signing_step_records_status_without_faking_or_failing_a_release(workflow_text):
    block = _step_block(workflow_text, "Record Authenticode signature status")
    assert "windows_release_evidence.py signing" in block
    assert "signing-status.json" in block
    # The step's own final statement, not an early return, is what neutralises the wrapper's
    # "exit $LASTEXITCODE": any native non-zero status must be replaced by an explicit 0.
    assert block.rstrip().endswith("exit 0"), "the signing step must end with an explicit exit 0"
    assert "exit $signingExit" not in block, ("the last exit code must be set deliberately, not inherited "
                                              "from the queried command")
    assert "$signingExit = $LASTEXITCODE" in block, "the native status must be snapshotted at the call"
    # Per-file detail goes to the step summary (uncapped) because annotations are capped at ten.
    assert "GITHUB_STEP_SUMMARY" in block and "signing-status.md" in block
    assert "if (Test-Path -LiteralPath $signingMarkdown)" in block, "the summary append must not assume the file exists"
    # Exactly two conditions may fail this step, and both are evidence-integrity failures
    # rather than signature findings: no record at all, and a record that cannot be parsed.
    assert block.count("throw") == 2, block
    assert "could not be recorded" in block and "malformed" in block
    assert "::error title=Signature record malformed::" in block
    assert "--annotate-title 'Signature verification produced no record'" in block, (
        "the no-record failure is annotated through the uncapped step-summary path, not a bare throw"
    )
    assert "::notice title=Signature status::" in block, (
        "the per-file signature states must stay readable without the artifact blob endpoint"
    )
    module_text = _read(ROOT / "packaging" / "windows_release_evidence.py")
    assert "Get-AuthenticodeSignature" in module_text
    assert "SignerCertificate.Subject" in module_text
    for forbidden in ("SignerCertificate.Thumbprint", "Get-PfxCertificate", "SecureString", "Export-Certificate"):
        assert forbidden not in module_text, f"{forbidden} risks publishing key material"


def test_acceptance_report_step_requires_independent_identity_and_lifecycle(workflow_text):
    block = _step_block(workflow_text, "Generate machine-readable Windows acceptance report")
    assert "--expected-innosetup-version $innoPin" in block
    assert "--require-lifecycle" in block
    assert "--lifecycle-report $lifecycleJson" in block
    assert "--signing-report $signingJson" in block
    assert "Get-Content -LiteralPath 'packaging\\inno_setup_version.txt'" in block
    assert "::notice title=Windows release manifest::" in block, (
        "the manifest identity and digests must stay readable when the artifact and log "
        "blob endpoints are unreachable"
    )
    assert "if: always()" in block or "if: always()" in workflow_text.split("Generate machine-readable Windows acceptance report", 1)[0][-200:]


@pytest.mark.parametrize("source", [
    ".github/workflows/windows-release-gate.yml",
    "docs/audits/m42-2-release-closure.json",
    "packaging/inno_setup_version.txt",
    "packaging/build_windows.ps1",
    "packaging/release_metadata.py",
    "packaging/acceptance_report.py",
    "packaging/windows_release_evidence.py",
])
def test_no_run_identifier_is_committed_into_release_sources(source):
    """Run ids are runtime facts; a committed one would be a fabricated verification value."""
    text = _read(ROOT / source)
    assert not re.search(r"actions/runs/\d{6,}", text), f"{source} embeds a GitHub run id"
    assert not re.search(r"\b\d{10,12}\b", text), f"{source} embeds what looks like a run id"


M422_CHECKPOINT = ROOT / "docs" / "audits" / "m42-2-release-closure.json"


def test_m42_2_checkpoint_records_provenance_correction_without_claiming_ci_results():
    """The M42.2 record names the defect and its guards, and asserts no CI outcome."""
    assert M422_CHECKPOINT.is_file()
    committed = M422_CHECKPOINT.read_text(encoding="utf-8")
    payload = json.loads(committed)
    assert payload["mission"] == "M42.2"
    assert payload["branch"] == "arena/01a0ec23-drill-master"
    assert payload["baseline"]["m42_1_final_sha"] == "64f7c82183b808f86af34a5c2663fc22c46eaa7f"
    defect = payload["innosetup_provenance_defect"]
    assert defect["published_value"] == "0.0.0.0"
    assert "reproduc" in defect["reproduction"].lower()
    assert defect["product_code_affected"] is False and defect["security_invariants_changed"] is False
    policy = payload["toolchain_identity_policy"]
    assert policy["single_source_of_truth"] == "packaging/inno_setup_version.txt"
    assert "0.0.0.0" in policy["rejected_values"] and "NOT_BUILT with an installer present" in policy["rejected_values"]
    assert len(policy["drift_cases_that_fail"]) >= 3
    assert payload["manifest_schema"]["before"] != payload["manifest_schema"]["after"]
    assert payload["installed_lifecycle"]["proves"] and payload["installed_lifecycle"]["does_not_prove"]
    assert payload["signing"]["current_status"] == "UNSIGNED"
    assert payload["signing"]["release_configuration_supports_signing"] is False
    assert payload["artifact_verification"]["shared_helper"].startswith("release_metadata.sha256_file")
    assert all(value == "NOT_RUN" for key, value in payload["external_acceptance"].items()
               if key != "synthetic_workbook_scenario")
    assert payload["external_acceptance"]["synthetic_workbook_scenario"] == "AUTOMATED_TEST_ONLY_NOT_REAL_DDR_ACCEPTANCE"
    gates = {item["gate"]: item["workflow_file"] for item in payload["internal_gates"]}
    assert set(gates) == {"source_release_gate", "windows_release_validation"}
    for relative in list(gates.values()) + [payload["runbook"], policy["single_source_of_truth"],
                                           "packaging/windows_release_evidence.py"]:
        assert (ROOT / relative).is_file(), relative
    for section in ("innosetup_provenance_defect", "artifact_verification", "installed_lifecycle"):
        for node_id in payload[section]["regression_guard"]:
            relative, _, test_name = node_id.partition("::")
            assert f"def {test_name}(" in (ROOT / relative).read_text(encoding="utf-8"), node_id
    assert "actions/runs/" not in committed and re.search(r"\b\d{10,}\b", committed) is None, (
        "run evidence is published by CI, never committed"
    )
    assert "m42-2-release-closure.json" in (ROOT / "PRODUCTION_READINESS.md").read_text(encoding="utf-8")


def test_runbook_documents_the_identity_lifecycle_and_signing_boundaries():
    """The human procedure must state the same boundaries as the machine evidence."""
    text = (ROOT / "packaging" / "WINDOWS_RELEASE_ACCEPTANCE.md").read_text(encoding="utf-8")
    for heading, required in (
        ("Inno Setup toolchain identity", ["inno_setup_version.txt", "innosetup.nuspec",
                                           "innosetup_compiler_file_version", "operator-attested"]),
        ("Installed-application lifecycle evidence", ["windows_release_evidence.py lifecycle", "/VERYSILENT",
                                                     "sentinel", "never simulated"]),
        ("Signature status", ["Get-AuthenticodeSignature", "UNSIGNED", "private key"]),
    ):
        assert heading in text, heading
        block = text.split(heading, 1)[1].split("\n###", 1)[0]
        # Markdown prose wraps; compare on normalized whitespace so a documented
        # boundary cannot be missed only because a line break fell inside it.
        normalized = " ".join(block.split())
        for fragment in required:
            assert fragment in normalized, f"{heading}: {fragment}"
    assert "no `path.read_bytes()`" in text or "never `path.read_bytes()`" in text
    assert "two independent builds" in text, "reproducibility must keep its explicit boundary"
