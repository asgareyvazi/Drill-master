"""Guard the Windows release gate's own contract (M42.1).

Two real Windows regressions motivated this file: a test read repository source
with the platform default encoding (cp1252 on the runner) and crashed with
``UnicodeDecodeError``, and per-failure annotations were silently truncated at
GitHub's ten-annotations-per-step limit.  Both are properties of the gate itself,
so they are asserted here rather than discovered by a red CI run.
"""
from __future__ import annotations

import ast
import importlib.util
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


_MODE_PATTERN = re.compile(r"[rwa][bt+]{0,2}")
# `os.open`/`os.fdopen`/`msvcrt.open_osfhandle` are descriptor syscalls: they take flags, never a text
# mode, so there is no encoding for them to declare and no Windows default for them to fall back to.
_RAW_DESCRIPTOR_OPENERS = frozenset({("os", "open"), ("os", "fdopen"), ("msvcrt", "open_osfhandle")})


def _unencoded_text_io_source(module: str, source: str) -> list[str]:
    """The rule itself, over source text, so the rule can be tested without editing a release tool.

    A guard that only ever runs against the current tree cannot be told apart from one that has quietly
    stopped matching anything, so the fixture-based self-check below feeds it code it must reject.
    """
    tree = ast.parse(source)
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
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if (func.value.id, "open") in _RAW_DESCRIPTOR_OPENERS:
                    continue
            # ``open(path, mode)`` takes the mode second; ``path.open(mode)`` takes it first; a handle
            # wrapper may take it anywhere, so any mode-shaped constant in the call is the declared mode.
            candidates = [node.args[1] if len(node.args) > 1 else None,
                          node.args[0] if len(node.args) else None]
            candidates += [kw.value for kw in node.keywords if kw.arg == "mode"]
            modes = [str(item.value) for item in candidates
                     if isinstance(item, ast.Constant) and _MODE_PATTERN.fullmatch(str(item.value) or "")]
            binary = any("b" in mode for mode in modes)
            if not binary and not any(kw.arg == "encoding" for kw in node.keywords):
                offenders.append(f"{module}:{node.lineno}: text-mode open() without encoding")
    return offenders


def _unencoded_text_io(module: str) -> list[str]:
    return _unencoded_text_io_source(module, (ROOT / module).read_text(encoding="utf-8"))


def test_the_encoding_guard_catches_text_opens_and_ignores_descriptor_syscalls():
    """Refining the encoding guard may not blind it, so its two halves are pinned on fixtures.

    M42.7 required an explicit encoding on every text read because the Windows default is cp1252; M42.9
    added descriptor-based opens (`io.open(fd, "rb")`, `os.open(name, flags, dir_fd=...)`) which carry no
    text mode at all.  Accepting those is correct, but only while a `open(path, "r")` is still rejected --
    which is what the fixture below proves, since a guard that stopped matching would also pass the tree.
    """
    caught = _unencoded_text_io_source("fixture.py", "with open(path, 'r') as handle:\n    return "
                                                     "handle.read()\n")
    assert caught and "text-mode open() without encoding" in caught[0]
    uncaught = _unencoded_text_io_source("fixture.py", "with io.open(fd, 'rb', closefd=True) as handle:"
                                                         "\n    return handle.read()\n"
                                                         "parent = os.open(root, flags)\n"
                                                         "return Path(x).read_text(encoding='utf-8')\n")
    assert uncaught == [], uncaught
    assert _unencoded_text_io_source("fixture.py", "return Path(x).read_text()\n"), "text reads stay caught"


def test_the_frozen_smoke_publishes_an_affirmative_marker_the_gate_can_read():
    """The lifecycle gate requires a marker; the application therefore has to emit one.

    A frozen windowed executable has no console, so the marker must reach the application
    log as well as stdout - otherwise the gate can only trust an exit code, which is the
    claim this guard exists to refuse.
    """
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "PACKAGE_SMOKE_OK" in source
    assert "logger.info(marker)" in source, "the marker must be written to the application log"
    smoke = source[source.index("def run_package_smoke"):source.index("def main()")]
    assert "print(marker)" in smoke
    assert "sys." not in smoke, (
        "run_package_smoke is executed in a restricted namespace by tests/test_credential_lifecycle.py, "
        "which supplies only os/Path/DatabaseManager/logger; a new module-level reference there fails "
        "the smoke for reasons unrelated to the product"
    )


def test_a_query_failure_keeps_its_reason_visible_in_the_published_evidence():
    """UNKNOWN without a reason is undiagnosable once the artifact endpoints are unreachable."""
    evidence = (ROOT / "packaging" / "windows_release_evidence.py").read_text(encoding="utf-8")
    assert "bound(error_text or output, 300)" in evidence, ("powershell reports the reason on stderr; "
                                                            "the record must carry it")
    assert "reason: " in evidence, "the step summary must publish each file's status message"
    # the cause has to survive a payload that parsed: that was the blind spot
    assert '"powershell_stderr"' in evidence, "bounded stderr must accompany a parseable payload"
    assert "required_field" in evidence, "a parseable payload with no required answer must be an error"
    assert "QueryError" in evidence, "the query script must report its own statement-level failure"
    assert "-ErrorAction Stop" in evidence, ("without Stop a cmdlet error stays non-terminating and "
                                            "the script still prints an empty answer")
    assert "_redact_tree(" in evidence, "published diagnostics must be redacted against credential values"
    assert "Get-Command Get-AuthenticodeSignature" in evidence, ("the host's capability must be probed "
                                                                 "and published")
    # counted on the flag rather than the bare module name, because prose in this file may name the
    # module too: what must stay at two is the number of scripts that actually import it
    assert evidence.count("Import-Module Microsoft.PowerShell.Security -ErrorAction") == 2, (
        "the profileless Windows PowerShell host does not auto-load the Security module - the runner "
        "proved it by reporting cmdlet=missing - so both the probe and the query must import it")
    assert "Import-Module Microsoft.PowerShell.Security -ErrorAction SilentlyContinue" in evidence, (
        "the per-file query keeps its import non-terminating: the cmdlet lookup answers for availability")
    assert '"security_module_import"' in evidence, "whether that import worked must itself be published"
    assert "try { Import-Module Microsoft.PowerShell.Security -ErrorAction Stop" in evidence, (
        "the import outcome must be the outcome of importing: a try/catch around the import itself.  "
        "Publishing the resolved-command lookup under this name is what let a record claim an import "
        "failure the host never reported")
    assert "module_import=$(if ($imported)" not in evidence and "$imported = [bool]" not in evidence, (
        "the import state must never be renamed from the Get-Command result; that single derivation "
        "is the ambiguity M42.6 was opened to correct, and restoring it would silently reinterpret "
        "every published record")
    assert "$probe.security_module_import = 'failed'" in evidence and "$_.Exception.Message" in evidence, (
        "a refused import must leave its bounded message in the record, not be discarded by Out-Null")
    assert '"cmdlet_available"' in evidence, ("availability is the only observation allowed to excuse "
                                              "a run from querying each file, so it needs its own field")
    assert '"probe_usable"' in evidence, "a diagnostic that broke must be distinguishable from a host that answered"
    for failure in ("subprocess.TimeoutExpired", 'powershell could not be started',
                    "powershell invocation failed"):
        assert failure in evidence, (f"a shell that never answered ({failure}) used to escape as a traceback, "
                                     "which left no record and let the gate blame a missing artifact")
    assert '"reason": bound(' in evidence, "the job console line must carry each non-pass reason"


def test_the_workflow_publishes_the_signature_cause_without_artifact_access():
    """A reviewer must be able to attribute the signing state from the job annotations alone."""
    workflow = (ROOT / ".github" / "workflows" / "windows-release-gate.yml").read_text(encoding="utf-8")
    assert "::notice title=Signature status::" in workflow
    assert "Signature state needs review" in workflow, ("an uninterpretable or broken signature is a "
                                                        "finding a reviewer should not have to notice "
                                                        "by reading a table")
    # the guard line itself, not just its title: an unconditional warning would be noise and a
    # removed one would leave a non-pass state unescalated
    assert "if (@('UNKNOWN', 'FAIL') -contains $signing.status) {" in workflow
    assert "$message = & $oneLine $_.status_message" in workflow, "the annotation must quote the recorded reason"
    assert "& $clip $message 160" in workflow, "the quoted reason must stay bounded"
    assert "Authenticode query environment" in workflow, "the step summary must record the query host"
    assert "security_module_import=$($signing.harness.security_module_import)" in workflow, (
        "the compact annotation line must carry the module-import outcome too: it is what separates "
        "a runner-image limitation from an answer about the shipped files")
    assert "cmdlet=$($signing.harness.query_command)" in workflow, (
        "availability travels beside the import outcome, never in place of it")
    assert "module_import=$($signing.harness.module_import)" not in workflow, (
        "the ambiguous key must not be read by the publication channel that replaced it")
    assert 'import_error=' in workflow, "a refused import must be quotable without the artifact endpoints"
    assert "$harness += ' import_error=' + (& $clip (& $oneLine $importError) 160)" in workflow, (
        "the host's message is joined after being flattened and clipped, never interpolated into the "
        "annotation line raw: the channel is one line and the annotation cap is real")
    # the recorded policy stays unchanged: a signature state never reddens the gate
    assert workflow.rstrip().endswith("exit 0") or "exit 0" in workflow.split("Signature status")[-1]


SHARED_SIGNING_CONTRACT_NAMES = ("SIGNING_STATUS_VOCABULARY", "SIGNING_FILE_VOCABULARY",
                                 "SIGNING_SCHEMA", "AUTHENTICODE_TO_FILE_STATUS",
                                 "aggregate_signing_status", "normalize_authenticode_status",
                                 "validate_signing_document")


def test_the_lifecycle_distinguishes_a_missing_uninstaller_from_a_vanished_one():
    """"Absent after install" and "gone before the uninstall ran" are different findings.

    A gate run failed on the second shape and the published record could only show a
    FileNotFoundError, which reads like a tool bug rather than an installer-tree change.  Both
    channels have to stay: the smoke step's deletion list, and the uninstall step's explicit
    before-and-after statement with the tree listing and the installer log tail.
    """
    evidence = (ROOT / "packaging" / "windows_release_evidence.py").read_text(encoding="utf-8")
    assert '"deleted_files_in_install_dir": deleted[:20]' in evidence, (
        "the installed smoke must report what disappeared from {app}, not only what appeared")
    assert "set(before) - set(after)" in evidence, "the deletion channel needs the inverse diff"
    assert "was present after install (installed_files) and is absent now" in evidence, (
        "the uninstall failure must say that the file was previously proved present")
    assert "for attempt in (1, 2):" in evidence, (
        "a listed-but-unlaunchable uninstaller gets exactly one bounded retry, no more")
    assert '"after a 2 second settle the uninstaller is "' in evidence, (
        "the re-listing after the settle is the part that separates busy from taken away")
    assert "installer log tail" in evidence, "and attach the installer's own closing lines"
    assert "return _finish(evidence, \"FAIL\", started)" in evidence, (
        "both paths end the lifecycle as a failure: neither is soft-pedalled")


def test_signing_vocabulary_and_extraction_rules_are_declared_exactly_once():
    """Two definitions of one vocabulary is how a gate starts disagreeing with itself.

    M42.4 widened this from the vocabulary alone to the whole signing contract: vocabulary,
    raw-status mapping, aggregation and document validation each have exactly one owner, and the
    producer and the consumer of the evidence both have to go through it.
    """
    packaging = Path(__file__).resolve().parents[1] / "packaging"
    sources = {path.name: ast.parse(path.read_text(encoding="utf-8"))
               for path in (packaging / "release_metadata.py", packaging / "acceptance_report.py",
                            packaging / "windows_release_evidence.py")}
    for name in SHARED_SIGNING_CONTRACT_NAMES:
        owners = []
        for module, tree in sources.items():
            for node in ast.walk(tree):
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                        owners.append(module)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                    # the producer may keep a wrapper of the same name, but only if it does
                    # nothing except call the single implementation
                    body = [statement for statement in node.body
                            if not (isinstance(statement, ast.Expr)
                                    and isinstance(statement.value, ast.Constant)
                                    and isinstance(statement.value.value, str))]
                    delegates = (module == "windows_release_evidence.py" and len(body) == 1
                                 and isinstance(body[0], ast.Return)
                                 and isinstance(body[0].value, ast.Call)
                                 and isinstance(body[0].value.func, ast.Name)
                                 and body[0].value.func.id == "signing_aggregate")
                    if not delegates:
                        owners.append(module)
        assert owners == ["release_metadata.py"], f"{name} defined in {owners}"
    for name in ("acceptance_report.py", "windows_release_evidence.py"):
        imported = {alias.name for node in ast.walk(sources[name]) if isinstance(node, ast.ImportFrom)
                    and node.module == "release_metadata" for alias in node.names}
        assert "SIGNING_SCHEMA" in imported, f"{name} must import the shared signing schema"
        assert {"aggregate_signing_status", "validate_signing_document"} & imported, (
            f"{name} must fold or validate signing evidence through the shared rule")
    # the evidence tool delegates rather than reimplementing, and keeps the name the report uses
    delegation = (packaging / "windows_release_evidence.py").read_text(encoding="utf-8")
    assert "return signing_aggregate(files)" in delegation, "aggregation must delegate to the shared rule"


def test_no_signing_consumer_reimplements_raw_windows_vocabulary():
    """A raw Authenticode spelling may only be interpreted in one place.

    Both sides used to compare strings such as ``NotSigned`` and ``Valid`` themselves, which is how
    a legitimate ``Unknown`` answer ended up folded into ``FAIL``.
    """
    packaging = Path(__file__).resolve().parents[1] / "packaging"
    contract = (packaging / "release_metadata.py").read_text(encoding="utf-8")
    assert '"notsigned": "UNSIGNED"' in contract and '"ok": "PASS"' in contract
    assert '"unknownerror": "UNKNOWN"' in contract, "an unknown Windows error must stay unknown"
    for name in ("acceptance_report.py", "windows_release_evidence.py"):
        source = (packaging / name).read_text(encoding="utf-8")
        for spelling in ("NotSigned", "NotTrusted", "HashMismatch", "UnknownError", '"Valid"', "'Valid'"):
            assert spelling not in source, f"{name} must not interpret the raw Windows state {spelling!r}"
    for module in ("acceptance_report.py", "windows_release_evidence.py", "release_metadata.py"):
        assert "drillmaster-signing-status/v1" not in (packaging / module).read_text(encoding="utf-8"), (
            f"{module} must not accept or emit the superseded signing schema")
    # the inner executable is only ever obtained through the archive-bound extraction helper
    evidence = (packaging / "windows_release_evidence.py").read_text(encoding="utf-8")
    assert "def extract_verified_member(" in evidence
    assert evidence.count("extract_verified_member(") >= 2
    assert 'release_root / exe_name' not in evidence, (
        "a loose release-directory copy must never stand in for the packaged executable"
    )


M424_CHECKPOINT = ROOT / "docs" / "audits" / "m42-4-authenticode-and-acceptance-closure.json"
M423_CHECKPOINT = ROOT / "docs" / "audits" / "m42-3-release-closure.json"


def test_m42_4_checkpoint_records_attribution_honestly_and_additively():
    """The checkpoint must state what was not verified, and correct M42.3 without rewriting it."""
    payload = json.loads(M424_CHECKPOINT.read_text(encoding="utf-8"))
    assert payload["mission"] == "M42.4" and payload["branch"] == "arena/01a0ec23-drill-master"
    attribution = payload["authenticode_attribution"]
    # the instrumented run answered the question, so the record must say so - while still refusing
    # to claim that the earlier un-instrumented run proved anything about itself
    assert attribution["status"] == "MECHANISM_CONFIRMED_BY_THE_INSTRUMENTED_RUN"
    assert attribution["confirmed_from_evidence"] is True
    assert attribution["kept_open_as_blocker"] is False
    assert "inference" in attribution["baseline_run_wording"], "the baseline run's own record carried no reason"
    assert attribution["still_open"], "a determinate verdict is still outstanding"
    assert attribution["followup_fix_applied"].startswith("both the capability probe")
    assert "module_import" in attribution["followup_fix_applied"]
    assert attribution["observed_record"]["harness"]["query_command"] == "missing"
    assert attribution["observed_record"]["aggregate"] == "UNKNOWN"
    assert len(attribution["retrieval_attempts"]) >= 3, "the blockers must be recorded, not summarised away"
    assert len(payload["not_verified"]) >= 5
    assert any("reproducib" in line.lower() for line in payload["not_verified"])
    assert [defect["id"] for defect in payload["defects"]] == ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8"]
    for defect in payload["defects"]:
        for key in ("symptom", "root_cause", "fix", "tests"):
            assert defect[key], f"{defect['id']} lost {key}"
        assert defect["tests"], f"{defect['id']} names no regression test"
    mutation = payload["mutation_validation"]
    assert mutation["caught"] == mutation["battery_size"] and mutation["survived"] == 0
    assert mutation["restored_after_run"] is True
    policy = payload["policy_preserved"]
    assert policy["unsigned_build_still_passes_the_internal_gate"] is True
    assert policy["unknown_never_relabelled_unsigned"] is True
    assert policy["zero_byte_files_remain_valid_hash_inputs"] is True
    assert payload["internal_gates"]["lint"]["debt_count"] <= payload["internal_gates"]["lint"]["debt_ceiling"]
    assert "ci" in payload["internal_gates"], "the checkpoint must say where the CI evidence lives"
    # the SHA the gate evidence belongs to is named, and the prose about CI can only refer to it
    verified = payload["internal_gates"]["verified_sha"]
    assert re.fullmatch(r"[0-9a-f]{40}", verified), verified
    assert verified in payload["internal_gates"]["ci"]
    assert "NOT gate-verified" in payload["internal_gates"]["ci"] or "no CI outcome is claimed" in \
        payload["internal_gates"]["ci"], "later commits must not inherit the earlier gate result"

    gates = payload["internal_gates"]["windows_gate_module_scope_local"]
    assert "libGL" in gates["failure_attribution"], (
        "every local failure must be attributed to a named environment limitation, not left as a bare count")
    assert gates["errors"] == 0 and gates["modules"] == 27
    # the vocabulary layers the report publishes are recorded, and NOT_VERIFIED stays out of the
    # Authenticode aggregate
    layers = payload["record_contract"]["vocabulary_layers"]
    assert "NOT_VERIFIED" not in layers["aggregate"] and "NOT_VERIFIED" not in layers["per_file"]
    assert "NOT_VERIFIED" in layers["report_absence"]
    assert "NOT_APPLICABLE" in layers["per_file"] and "NOT_RUN" in layers["aggregate"]

    # M42.3 is corrected additively: its dated wording survives next to the new key
    m423 = json.loads(M423_CHECKPOINT.read_text(encoding="utf-8"))
    correction = m423["correction"]
    assert correction["recorded_by"] == "M42.4" and correction["supersedes_this_record"] is False
    assert "UNSIGNED" in m423["signing_contract"]["current_status"], "the dated record must survive verbatim"
    assert correction["affected_statement"].startswith("signing_contract.current_status")
    assert "UNKNOWN" in correction["what_the_exact_sha_run_recorded"]
    for field in correction["fields_left_unchanged"]:
        assert field in m423, f"the additive correction lost or altered {field}"


def test_the_owner_decisions_stay_open_and_named_in_both_records():
    """Four decisions and six P6 items are neither closable by code nor silently dropped."""
    checkpoint = json.loads(M424_CHECKPOINT.read_text(encoding="utf-8"))
    decisions = checkpoint["acceptance_readiness"]["open_owner_decisions"]
    for label in ("A:", "B:", "C:", "D:"):
        assert any(item.startswith(label) for item in decisions), label
    for identifier in ("NEW-P6-007", "NEW-P6-008", "NEW-P6-015", "NEW-P6-020", "NEW-P6-023", "NEW-P6-024"):
        assert identifier in decisions and identifier in (ROOT / "PRODUCTION_READINESS.md").read_text(encoding="utf-8")
    handoff = (ROOT / "PRODUCTION_READINESS.md").read_text(encoding="utf-8")
    section = handoff[handoff.index("### Decisions required from the owner"):]
    for row in ("| A |", "| B |", "| C |", "| D |"):
        assert row in section, f"the handoff decision table lost row {row}"
    register = (ROOT / "packaging" / "WINDOWS_RELEASE_ACCEPTANCE.md").read_text(encoding="utf-8")
    for row in ("REL-01", "REL-02", "REL-03", "REL-04", "REL-05", "REL-06", "REL-07",
                "REL-08", "REL-09", "REL-10", "REL-11", "REL-12"):
        assert row in register, f"the acceptance register lost {row}"
    for column in ("prerequisite", "required evidence", "pass condition", "owner", "status"):
        assert column in register, f"the register lost the {column!r} column"


def test_runbook_documents_the_archive_bound_signing_and_required_record_contract():
    text = (Path(__file__).resolve().parents[1] / "packaging" / "WINDOWS_RELEASE_ACCEPTANCE.md").read_text(encoding="utf-8")
    for fragment in ("extracted from the portable archive", "container_archive_sha256",
                     "not examined, because nothing binds it", "--require-signing",
                     "Signature record malformed", "PACKAGE_SMOKE_OK"):
        assert fragment in text, f"runbook must document: {fragment}"
    m424 = ("drillmaster-signing-status/v2", "release_metadata_sha256", "QueryError",
            "Get-Command Get-AuthenticodeSignature", "Signature state needs review",
            "powershell_stderr", "raw_status_recognized", "Acceptance register",
            "never executes a downloaded binary", "Get-FileHash", "Expand-Archive",
            "AUTOMATED_TEST_ONLY_NOT_REAL_DDR_ACCEPTANCE")
    missing = [fragment for fragment in m424 if fragment not in text]
    assert not missing, f"runbook must document the M42.4 contract and procedures: {missing}"
    # the procedure must stay runnable without the repository and must forbid execution
    section = text[text.index("## Re-verifying a downloaded artifact yourself"):text.index("## Acceptance register")]
    assert "Get-AuthenticodeSignature" in section and "SHA256SUMS.txt" in section
    assert "Do\nnot run" in section or "not run `DrillMaster.exe`" in section.replace("\n", " ").replace(
        "Do not run `DrillMaster.exe`", "not run `DrillMaster.exe`")
    for row in ("REL-01", "REL-03", "REL-04", "REL-07", "REL-09", "REL-12"):
        assert row in text, f"acceptance register lost row {row}"


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
    "docs/audits/m42-3-release-closure.json",
    "docs/audits/m42-4-authenticode-and-acceptance-closure.json",
    "docs/audits/m42-5-release-closure-and-signature-settlement.json",
    "docs/WINDOWS_ACCEPTANCE.md",
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
M425_CHECKPOINT = ROOT / "docs" / "audits" / "m42-5-release-closure-and-signature-settlement.json"


def test_m42_5_checkpoint_settles_authenticode_without_promoting_anything():
    """The M42.5 record must carry the observed signature line, the per-SHA gate truth, and its limits.

    It is guarded so a later edit cannot quietly upgrade UNKNOWN to a verdict, drop the artifact blocker, or
    let one packaging status promote another.
    """
    payload = json.loads(M425_CHECKPOINT.read_text(encoding="utf-8"))
    assert payload["mission"] == "M42.5" and payload["branch"] == "arena/01a0ec23-drill-master"
    settlement = payload["authenticode_settlement"]
    assert settlement["status"] == "MECHANISM_CONFIRMED_ON_THE_RELEASE_CANDIDATE_SHA"
    assert "module_import=failed" in settlement["observed_record"]
    assert "not renamed to UNSIGNED" in settlement["decision_rule_applied"]
    assert re.fullmatch(r"[0-9a-f]{40}", settlement["verified_sha"])
    assert settlement["verified_sha"] == payload["internal_gates"]["verified_sha"]
    for gate in ("source_gate", "windows_gate"):
        assert "success" in payload["internal_gates"][gate]["outcome"]
        assert "exact SHA" in payload["internal_gates"][gate]["outcome"], (
            "the gate sentence must bind itself to the SHA under verification")
    assert payload["internal_gates"]["runs_on_earlier_candidates"], "failed candidates must stay on the record"
    push_state = payload["internal_gates"]["push_state"]
    assert settlement["verified_sha"] in push_state, (
        "the gate-verified SHA must be named, so a later commit cannot inherit its result by silence")
    assert "NOT" in push_state.upper() or "cannot inherit" in push_state
    mutation = payload["mutation_validation"]
    assert mutation["caught"] == mutation["entries"] and mutation["survived"] == 0
    assert mutation["restored"] is True and mutation["honest_limit"], "a subset is not an exhaustive proof"
    blocker = payload["independent_artifact_reverification"]
    assert blocker["status"] == "BLOCKED"
    assert "SSL_ERROR_SYSCALL" in blocker["transport_evidence"] and "401" in blocker["second_blocker"]
    assert "no bytes were downloaded" in blocker["not_done"]
    matrix = payload["packaging_status_matrix"]
    # the eight statuses stay separate, and the two that cannot follow from a green gate do not
    assert matrix["portable_bundle_build"] == matrix["installer_compilation"] == "PASS"
    assert matrix["independent_artifact_hash_recomputation"] == "BLOCKED"
    assert matrix["interactive_clean_machine_install_accepted"] == "NOT_RUN"
    assert matrix["production_acceptance"] == "NOT_RUN"
    assert matrix["trusted_code_signing"].startswith("NOT_ESTABLISHED")
    external = payload["external_obligations"]
    assert external["states"]["real_ddr_excel_acceptance"] == "NOT_RUN"
    assert external["synthetic_workbook"] == "AUTOMATED_TEST_ONLY_NOT_REAL_DDR_ACCEPTANCE"
    assert len(payload["not_verified"]) >= 4
    for correction in payload["corrections"]:
        if str(correction["target"]).startswith("docs/audits/"):
            assert "additive" in correction["nature"], (
                "an earlier mission's record may be corrected alongside, never overwritten")
    assert "no_invention" in payload["state_discovery_and_recovery"]
    for defect in payload["phase_b_review"]["defects_found_and_fixed"]:
        assert defect["detail"] and defect["fix"] and defect["tests"], f"{defect['id']} is under-evidenced"


def test_the_attribution_correction_is_kept_in_the_record_and_in_every_channel():
    """A corrected claim must stay corrected, in the code and in the documents that repeated it.

    M42.5 published an availability observation under the name of an import observation and inferred a
    refused module load from it.  This guard exists so that inference cannot come back through a
    reworded record, a dropped table row, or a channel that only prints the old field.
    """
    def flat(text):
        return " ".join(text.split())

    payload = json.loads(M425_CHECKPOINT.read_text(encoding="utf-8"))
    assert payload["missions"] == ["M42.5", "M42.6"], "the record covers both missions by name"
    correction = payload["m42_6_release_closure"]["attribution_correction"]
    for key in ("defect", "why_it_mattered", "corrected_observations", "decision_table", "never_permitted",
                "schema_decision", "channels_updated"):
        assert correction[key], f"the correction record is incomplete without {key}"
    assert "Get-Command" in correction["defect"] and "Out-Null" in correction["defect"]
    settlement = payload["authenticode_settlement"]
    leading_rule = settlement["decision_rule_applied"].split(".")[0]
    assert "could not import" not in leading_rule, (
        "the rule as stated up front must be the supported one; the superseded wording is allowed only "
        "inside the correction that names it as superseded")
    assert "[M42.6 correction]" in settlement["decision_rule_applied"], (
        "the correction must be visible beside the claim it replaces, not in a separate document")
    assert "unavailable capability" in flat(settlement["decision_rule_applied"]), \
        "the record must state what is actually proven"
    closure = payload["m42_6_release_closure"]
    gates = closure["internal_gates"]
    assert gates["verified_sha"] != settlement["verified_sha"], (
        "the corrected record names the SHA its own gates ran on; reusing the earlier mission's SHA "
        "would let a pre-correction result be read as proof of the correction")
    for channel in ("source", "windows", "windows_suite", "published_manifest_notice",
                    "this_commit_is_records_only"):
        assert gates[channel], f"the gate record is incomplete without {channel}"
    assert "completed/success" in gates["source"] and "head_sha equal to the published SHA" in gates["source"], (
        "a run on some other SHA is not evidence about this one")
    assert "conclusion success" in gates["windows"] and "lifecycle=PASS" in gates["windows"]
    reverification = closure["independent_artifact_reverification"]
    assert reverification["verdict"] == "BLOCKED"
    assert "no bytes were downloaded" in reverification["not_done"], (
        "a blocked transport must be reported as blocked, never as a verification that passed")
    assert "SSL_ERROR_SYSCALL" in reverification["transport_evidence"]
    assert "321705858" in reverification["artifact_identity"]
    signing = closure["signing_trust_and_lifecycle"]
    observed = signing["observed_after_correction"]
    assert "security_module_import=failed" in observed and "cmdlet=missing" in observed, (
        "the two observations must be quotable separately from the published record")
    assert "corroborate" in signing["what_the_two_observations_now_mean"], (
        "an observation that happens to agree with an earlier unproven claim is not the same kind of claim")
    assert "NOT_ESTABLISHED" in signing["signing_trust"]
    local = closure["local_verification"]
    for claim in (local["focused"], local["release_relevant_scope"]):
        collected = re.search(r"(\d+) collected, (\d+) passed, (\d+) failed", claim)
        assert collected, "the local record must state its counts, not just its conclusions"
        assert collected.group(1) == collected.group(2) or "libGL.so.1" in claim, (
            "a shortfall is only acceptable when the record names the environmental cause")
    assert "libGL.so.1" in local["release_relevant_scope"], (
        "an environmental failure must be named as one, with its count")
    assert "measured on the tree of the gated code SHA" in local["focused"], (
        "a count without the tree it was taken on is a number, not evidence")
    assert "5375" in local["lint"] and "not lint-clean" in local["lint"]
    assert closure["state_discovery_and_recovery"]["classification"].startswith("STATE-B")
    assert "no_destructive_command_used" in closure["state_discovery_and_recovery"]
    battery = closure["correction_validation"]["mutation_battery"]
    assert battery["survived"] == 0 and battery["caught"] == battery["attempted"] and battery["honest_limit"]
    assert battery["first_run"], "the survivors this mission found in its own tests stay on the record"

    assert "module_import=failed" in settlement["observed_record"], (
        "what the runs printed stays quoted verbatim; only the reading of it changes")
    assert "verbatim" in settlement["observed_record_note"]
    assert any("correction" in item["nature"] and "authenticode_settlement" in item["target"]
               for item in payload["corrections"]), "the correction must be listed as a correction"
    for defect in payload["phase_b_review"]["defects_found_and_fixed"]:
        if defect["id"] == "M42.5-B2":
            assert "M42.6 correction" in defect["detail"] and "M42.6 correction" in defect["fix"]
    m424 = json.loads(M424_CHECKPOINT.read_text(encoding="utf-8"))
    followup = m424["m42_5_followup"]["superseded_by_this_followup"][-1]
    assert "renamed" in followup and "attribution_correction" in followup, (
        "the M42.4 followup cited the reproduction as proof about the import; it must cite the correction")

    runbook = (ROOT / "packaging" / "WINDOWS_RELEASE_ACCEPTANCE.md").read_text(encoding="utf-8")
    assert "| `failed` | available |" in runbook, "the table row that decides the hard case must stay"
    assert "never produces a statement about the files" in flat(runbook), (
        "the runbook must state what a missing cmdlet may not be read to mean")
    assert "harness.module_import" in flat(runbook), (
        "the superseded field name has to stay named where the correction is explained, or a reader "
        "of the old records has nothing to reconcile them against")
    for overclaim in ("import outcome is reported from the command lookup",
                      "module_import=failed` proves the module could not be loaded",
                      "the harness could not import Microsoft.PowerShell.Security, so the cmdlet"):
        assert overclaim not in flat(runbook), (
            f"the runbook must not state {overclaim!r}: that is the inference this mission corrected")

    readiness = (ROOT / "PRODUCTION_READINESS.md").read_text(encoding="utf-8")
    for overclaim in ("the field that separates a runner-image limitation from an answer about the "
                      "shipped files",
                      "publish the harness module-import field, which separates a runner-image limitation"):
        assert overclaim not in flat(readiness), (
            f"the living summary must not restore {overclaim!r}, which reads an availability field as "
            "an import observation")
    assert "computed from the command lookup and never from the import itself" in flat(readiness), (
        "the living summary must keep the correction, not the superseded inference")
    assert "The quoted string remains what those runs published" in flat(readiness), (
        "the correction must not be written as if the earlier observation were false")

    evidence = (ROOT / "packaging" / "windows_release_evidence.py").read_text(encoding="utf-8")
    for field in ("security_module_import", "cmdlet_available", "probe_usable"):
        assert field in evidence, f"{field} must be published by the generator"
    assert "Import outcome and command availability are separate observations" in flat(evidence), (
        "the rule has to travel with the fields, not live only in the test")


def test_the_lifecycle_instability_is_recorded_without_relaxing_any_protection():
    """A red gate on a records commit is written up, not explained away or softened.

    The register row exists so the next reviewer sees that the lifecycle step can fail on identical
    code, and the guards below exist so that seeing it cannot become a reason to drop the retry, the
    empty-`{app}` proof, or the second-refusal failure.
    """
    runbook = (ROOT / "packaging" / "WINDOWS_RELEASE_ACCEPTANCE.md").read_text(encoding="utf-8")
    assert "| REL-13 |" in runbook, "the instability needs an owner-visible row, not a footnote"
    assert "install tree holds 0 file(s)" in runbook, (
        "the diagnostic must distinguish an external removal from a launch failure")
    assert "must not be relaxed to obtain green" in runbook
    assert "re-run the identical SHA and record both attempts" in runbook, (
        "the prescribed response has to be named, or the row invites a silent retry until green")

    evidence = (ROOT / "packaging" / "windows_release_evidence.py").read_text(encoding="utf-8")
    assert "for attempt in (1, 2):" in evidence, "exactly one bounded retry, no more"
    assert "install tree holds" in evidence, "the tool must publish the tree state it observed"
    assert "def install_tree_note" in evidence or "install_tree_note(" in evidence

    payload = json.loads(M425_CHECKPOINT.read_text(encoding="utf-8"))
    instability = payload["m42_6_release_closure"]["lifecycle_instability_observed"]
    for key in ("what_happened", "what_it_proves", "what_it_does_not_prove", "response",
                "consequence_for_the_verdict"):
        assert instability[key], f"the finding is incomplete without {key}"
    assert "no threshold" in instability["response"].lower()
    assert "antivirus" in instability["what_it_does_not_prove"], "the suspicion must stay a suspicion"
    assert "must come from a run of that SHA" in instability["consequence_for_the_verdict"]


FORENSIC_SAMPLE_LABELS = ("pre_launch", "uninstaller_absent_before_launch", "after_refusal_",
                          "after_settle", "launch_error_")


def test_the_lifecycle_forensics_are_additive_and_keep_every_protection():
    """The M42.7 diagnostics may add observations; they may not buy a pass with them.

    Sampling is the only thing the lifecycle step gained, so the guards are about adjacency: the work
    root is still deleted afterwards, the uninstall still has to empty `{app}`, the launch is still
    retried exactly once, the sampler writes and executes nothing of its own, and the block is
    published inside `diagnostics`, which the report already forwards -- so the evidence file's schema
    name is unchanged instead of silently redefined.
    """
    evidence = (ROOT / "packaging" / "windows_release_evidence.py").read_text(encoding="utf-8")
    for fragment in ('evidence["diagnostics"]["uninstall_forensics"] = samples',
                     "def _uninstall_forensics(", "def _observed_path(", "def _forensic_note(",
                     "def _forensic_brief(", "samples[label] = _redact_tree(sample, secret_values)",
                     "for attempt in (1, 2):", 'evidence["cleaned_up"] = not work_root.exists()'):
        assert fragment in evidence, f"the forensic contract lost {fragment!r}"
    for label in FORENSIC_SAMPLE_LABELS:
        assert label in evidence, f"the sample labelled {label!r} is gone"
    # the two read-only helpers as one span: observation must not touch permissions, create, delete or run
    sampler = evidence[evidence.index("def _observed_path("):evidence.index("def _forensic_brief(")]
    # call forms rather than words: these docstrings talk about "touching" a file, and a guard that
    # matched vocabulary would test the prose instead of the code
    for forbidden in ("mkdir(", "touch(", "chmod(", "write_text(", "write_bytes(", "unlink(", "remove(",
                      "rename(", "replace(", "rmtree(", "symlink_to(", "open(", "subprocess.", "runner(",
                      "Popen(", "os.", "shutil."):
        assert forbidden not in sampler, f"the sampler must only read; found {forbidden!r}"
    assert '"drillmaster-installer-lifecycle/v1"' in evidence, ("additive fields are fine; a redefined "
                                                                "schema name would make published records lie")
    assert '"install_dir_emptied": not sorted(snapshot(install_dir))' in evidence, (
        "an exit code is still not evidence that the uninstall worked")
    assert "MAX_FORENSIC_HASH_BYTES" in evidence, "hashing must stay bounded, never silently unbounded"


def test_the_forensic_findings_reach_both_published_channels():
    """A detail that clips away its own labels is not evidence, so the summary and the block must agree."""
    evidence = (ROOT / "packaging" / "windows_release_evidence.py").read_text(encoding="utf-8")
    assert 'evidence["uninstall_launch_notes"] = bound("; ".join(notes), 1200)' in evidence
    assert ('evidence["diagnostics"]["uninstall_launch_notes"] = '
               'evidence["uninstall_launch_notes"]') in evidence
    assert "full notes in uninstall_launch_notes" in evidence
    assert "samples in diagnostics.uninstall_forensics" in evidence
    report = (ROOT / "packaging" / "acceptance_report.py").read_text(encoding="utf-8")
    assert '"diagnostics": payload.get("diagnostics") or {}' in report, "the sampler's channel is forwarding"
    assert '"steps": steps' in report, "the summary's channel is the step list"
    runbook = (ROOT / "packaging" / "WINDOWS_RELEASE_ACCEPTANCE.md").read_text(encoding="utf-8")
    assert "### Lifecycle failure forensics (M42.7)" in runbook
    for fragment in ("host_side_evidence", "`pre_launch`", "after_refusal_1", "never attributed",
                     "64 MB", "st_file_attributes", "installer and uninstaller logs",
                     "WinError 2"):
        assert fragment in runbook, f"the runbook stopped documenting {fragment!r}"


def test_rel_04_names_the_external_match_without_borrowing_any_trust():
    """The MATCH belongs to one reviewer, one artifact, and nothing else -- and says so in the row.

    The row is written so that a reader cannot lift it into an in-repository verification, a trust
    statement, or coverage of a later artifact: the in-repository status, the tip's own artifact, and
    the built report's `NOT_VERIFIED` are all named in the same cell.
    """
    runbook = (ROOT / "packaging" / "WINDOWS_RELEASE_ACCEPTANCE.md").read_text(encoding="utf-8")
    row = next(line for line in runbook.splitlines() if line.startswith("| REL-04 |"))
    assert "`NOT_RUN` in-repository (`NOT_VERIFIED` in the report)" in row, "the in-repository status stays"
    assert "external** reviewer ran the procedure" in row
    assert "for **those bytes only" in row, "the scope of a MATCH has to be stated where it is read"
    assert "11696022238" in row and "38122859040" in row, "the artifact and run the MATCH covers"
    assert "`11696578929` is unverified" in row
    assert "independent_reverification=NOT_VERIFIED" in row
    assert "reset" in row, "why the repository could not confirm it is part of the record"
    rel13 = next(line for line in runbook.splitlines() if line.startswith("| REL-13 |"))
    assert "diagnostics.uninstall_forensics" in rel13 and "did not reproduce" in rel13
    assert "cause stands as undetermined" in rel13
    assert "`OPEN`" in rel13, "an explained incident is not a closed one"


def test_log_tails_are_bounded_reads_and_never_whole_file_reads():
    """The M42.8 contract: cost is bounded at the read, and every lifecycle log read is inside the root.

    `bound()` on the published string was never a statement about I/O, so the shape of the reader is
    pinned here as well as exercised by the byte counter in the behavioural suite: one seek-windowed
    read, one explicit bound, and no whole-file `read_text` left on any lifecycle path.  Each call
    site has to name the root it is reading inside, because "it is only a log file" is exactly how a
    replaced path stops being only a log file.
    """
    evidence = (ROOT / "packaging" / "windows_release_evidence.py").read_text(encoding="utf-8")
    reader = evidence[evidence.index("def _bounded_tail("):evidence.index("def _tail(")]
    opener = evidence[evidence.index("def _open_binary("):evidence.index("def _bounded_tail(")]
    assert "stream.seek(0, os.SEEK_END)" in reader and "stream.seek(start - probe)" in reader, (
        "the window must be sought from the end, not read and sliced")
    assert "read_text" not in reader, "a whole-file read on the failure path is the defect being fixed"
    assert "stream.read(byte_limit + 1)" in reader, ("the read stays at the ceiling plus the one boundary "
                                                     "probe byte; asking for more is how the bound is evaded")
    assert "stream.read(byte_limit + 2)" not in reader, "no second spare byte, and no unbounded probe"
    assert "path.stat()" not in reader and "path.is_file()" not in reader, (
        "the reader decides about the opened object; a second look at the name is the check this replaces")
    assert "_open_binary(path, permitted_root, root_identity)" in reader, (
        "the tail is read through the anchored open, not through a name that was validated earlier")
    assert "_is_within" not in reader, ("containment may not be decided by resolving a name first: that is "
                                        "the check this replaced, and it can only be fooled, never relied on")
    assert 'raise ValueError("byte_limit must be a positive bound")' in reader
    assert "byte_limit cannot exceed the global tail bound" in reader, (
        "LOG_TAIL_BYTES is a ceiling, so an oversized override has to be refused, not clamped or honoured")
    assert "_READ_STATES = frozenset({" in evidence, "the read states are a documented vocabulary, not ad hoc strings"
    for state in ('"complete"', '"truncated"', '"empty"', '"absent"', '"unreadable"', '"skipped_unsafe_path"'):
        assert state in evidence, f"{state} left the documented read vocabulary"
    assert "refusal.state in _READ_STATES" in reader, ("a refusal may only publish a documented state; an "
                                                        "undecodable one becomes 'unreadable', never 'complete'")
    assert "older content was not inspected" in reader, "a suffix must never be presented as the log"
    assert "dropped_partial_first_line" in reader
    assert 'boundary != b"\\n"' in reader, ("the first line is partial only when the byte before the window "
                                            "says so; an aligned window keeps its first line")
    assert "grew_during_read" in reader, "growth past the measured end has to be reported, not clipped away"
    for anchor in ("getattr(os, \"O_NOFOLLOW\", 0)", "dir_fd=parent_fd", "stat.S_ISREG",
                   'getattr(os, "O_NONBLOCK", 0)'):
        assert anchor in opener, f"the anchored open lost {anchor!r}, which is the half that closes the race"
    for windows_call in ("GetFinalPathNameByHandleW", "GetFileInformationByHandle", "GetFileType",
                         "_WIN32_FILE_ATTRIBUTE_REPARSE_POINT"):
        assert windows_call in evidence, (f"{windows_call} is how the Windows side binds the verdict to the "
                                          "handle; `O_NOFOLLOW` is not a Windows guard and is not treated as one")
    assert "if os.name == \"nt\"" in evidence or "os.name == \"nt\"" in opener, (
        "the two platforms need different anchors, and neither may be pretended for the other")

    module_lines = evidence.splitlines()
    reads = [line for line in module_lines if "_tail(" in line or "_bounded_tail(" in line]
    calls = [line for line in reads if "def " not in line and "permitted_root=" not in line]
    assert not calls, "every lifecycle log read must name its permitted root:\n" + "\n".join(sorted(calls))
    assert "LOG_TAIL_BYTES = 512 * 1024" in evidence, "the bound is policy; a default that drifted would be silent"
    behaviour = (ROOT / "tests" / "test_windows_release_evidence.py").read_text(encoding="utf-8")
    assert behaviour.count('read_counter["bytes"] <=') >= 6, ("bounded I/O is measured independently in the "
                                                              "large-log, single-line, multibyte, ceiling and "
                                                              "refusal cases; a count that drops means one "
                                                              "measurement was deleted, and any single assertion "
                                                              "is easy to weaken into a string-length check")
    assert 'module._tail(log, 6, permitted_root=root)' in behaviour, ("the bound has to be measured through the "
                                                                      "wrapper the lifecycle step actually calls, "
                                                                      "not only through the dict-returning helper "
                                                                      "the tests prefer")
    assert 'read_counter["bytes"] == 0' in behaviour, ("a refused read is measured at zero bytes, not "
                                                        "asserted from a reason string")


def test_every_lifecycle_log_read_names_the_root_identity_it_is_confined_to():
    """`permitted_root=` names a *path*; the identity is what proves the path still denotes the same root.

    The M42.9 record and the living summary both promise that the work root's identity is captured once and
    re-validated by every anchored open, so a read that supplies only the path is confined to whatever that
    path denotes when the read happens -- the substitution the anchor exists to refuse.  Two diagnostic reads
    did exactly that (the installer-log tail on the absent-uninstaller path, and the uninstall log inside
    `_uninstall`); they are threaded through by name, and this pins the shape so the next call site cannot
    quietly reintroduce it.  A window of three lines is inspected because the calls are wrapped across lines
    by formatting, not because the requirement is loose.
    """
    evidence = (ROOT / "packaging" / "windows_release_evidence.py").read_text(encoding="utf-8")
    lines = evidence.splitlines()
    indexes = [index for index, line in enumerate(lines)
               if ("_tail(" in line or "_bounded_tail(" in line) and "def " not in line]
    assert len(indexes) >= 5, "the reader call sites are the thing being guarded; finding none is a finding"
    for index in indexes:
        window = "\n".join(lines[index:index + 3])
        assert "permitted_root=" in window, (
            f"the read at line {index + 1} names no permitted root:\n{window}")
        assert "root_identity=" in window, (
            f"the read at line {index + 1} never compares the root's identity, so it is confined to "
            f"whichever directory that path denotes at read time:\n{window}")


def test_diagnostic_failures_cannot_replace_a_lifecycle_failure():
    """Sampling is subordinate: it reports its own trouble, it never becomes the finding.

    The sampler runs from inside an exception handler, so an uncaught error there would surface as a
    crash of the step and lose the launch error it was meant to describe.  Two shapes are pinned: the
    file-level classification of a failed read, and the handler that turns any *unexpected* sampler
    defect into a published `sampler_failed` observation while the lifecycle result stands.
    """
    evidence = (ROOT / "packaging" / "windows_release_evidence.py").read_text(encoding="utf-8")
    sampler = evidence[evidence.index("def forensics(label"):evidence.index('forensics("pre_launch")')]
    assert "except Exception as exc" in sampler and "sampler_failed" in sampler
    assert "diagnostics unavailable" in sampler, "the detail must say the sample failed, not that it was empty"
    assert 'return _finish(evidence, "FAIL", started)' in evidence, "the refusal still fails the step"
    for channel in ('"read_state"', '"bytes_read"', '"read_reason"'):
        assert channel in evidence, f"the log sample stopped publishing {channel}"
    for line in ('state["read_state"] = observed["state"]',
                 'state["bytes_read"] = observed["bytes_read"]',
                 'if observed["reason"]:'):
        assert line in evidence, ("the classification has to be copied through log_state verbatim; a dropped "
                                  f"line turns an unknown read into an unremarkable one: {line}")
    assert evidence.count('state["exists"] = path.is_file()') == 1
    assert "size_error" not in evidence, "the size moved into the reader, where the handle is the source"
    entries = evidence[evidence.index("def _uninstall_forensics("):evidence.index("def _forensic_brief(")]
    assert entries.count("snapshot(install_dir)") == 1, ("the count and the names must come from one listing, "
                                                        "not two filesystem moments")
    assert "resolves outside the permitted evidence root; not hashed" in evidence


def test_m42_7_followup_records_the_closure_without_promoting_anything():
    """A follow-up may settle what happened; it may not turn an external result or a green gate into trust.

    These guards exist so a later edit cannot promote `MATCH_REPORTED_BY_EXTERNAL_REVIEWER` into
    in-repository verification, `UNKNOWN` into a signature verdict, a cancelled run into a failure or a
    pass, or a green gate on one SHA into a claim about the tip that carries the record.  Counts inside
    the block are checked as shapes, and only the scope claim whose environmental cause is named may
    carry a shortfall -- the lesson from the mission whose guard falsified the number it pinned.
    """
    payload = json.loads(M425_CHECKPOINT.read_text(encoding="utf-8"))
    assert payload["mission"] == "M42.5" and payload["branch"] == "arena/01a0ec23-drill-master"
    followup = payload["m42_7_followup"]
    assert followup["mission"] == "M42.7" and followup["recorded_on"] == "2026-10-11"
    assert "additively" in followup["why_this_is_a_followup_and_not_a_new_audit"] or \
        "nothing above this key is edited" in followup["why_this_is_a_followup_and_not_a_new_audit"]

    # the earlier blocked record keeps its own verdict: a follow-up adds, it does not rewrite
    closure = payload["m42_6_release_closure"]
    assert closure["independent_artifact_reverification"]["verdict"] == "BLOCKED"
    assert "no bytes were downloaded" in closure["independent_artifact_reverification"]["not_done"]

    recovery = followup["workspace_state_and_recovery"]
    for key in ("entry_state", "how_the_tip_was_established", "post_reset_state", "false_alarm_recorded"):
        assert recovery[key], f"the recovery story is incomplete without {key}"
    assert "git reset --hard" in recovery["commands_not_used"] and "force push" in recovery["commands_not_used"]
    assert "0 entries" in recovery["post_reset_state"] and "926" in recovery["post_reset_state"]

    method = followup["gate_readback_method"]
    assert "actions/runs?head_sha=" in method["authoritative_channel"] and "?branch=" in method["authoritative_channel"], \
        "a push-triggered run is read from the run list, never from a PR-only view"
    assert "proves nothing in either direction" in method["pr_only_interfaces_are_not_proof"]
    assert "cancelled" in method["cancelled_is_not_failed"] and "superseded" in method["cancelled_is_not_failed"]
    assert "never promoted to a later tip" in method["identity_rule"]

    tip = followup["gates_on_the_incoming_tip"]
    assert re.fullmatch(r"[0-9a-f]{40}", tip["sha"]), "a gate claim must name a full SHA"
    assert tip["source_release_gate"]["conclusion"] == "success" == tip["windows_release_validation"]["conclusion"]
    assert tip["source_release_gate"]["event"] == "push" and tip["source_release_gate"]["attempt"] == 1
    assert tip["windows_release_validation"]["step_conclusions"] == "all success"
    assert "lifecycle smoke" in tip["windows_release_validation"]["lifecycle_step"]
    assert tip["artifact_published_by_this_tip"]["independent_byte_verification"].startswith("NOT_VERIFIED")
    assert "proves nothing about Authenticode trust" in tip["what_this_proves_and_does_not"]

    match = followup["independent_artifact_match"]
    assert match["status"] == "MATCH_REPORTED_BY_EXTERNAL_REVIEWER"
    assert "did NOT run a verifier" in match["performed_by"]
    assert "m426_independent_artifact_verification.json" in match["performed_by"], \
        "an absent file must be named as absent, never cited as opened"
    assert match["binary_executed"] is False
    assert "drillmaster-release-artifacts/v2" == match["manifest"]["schema"]
    assert len(match["container"]["sha256"]) == 64 and len(match["inner_executable"]["sha256"]) == 64
    joined = " ".join(match["what_it_does_not_change"])
    for fragment in ("stays NOT_RUN", "NOT_VERIFIED", "NOT_ESTABLISHED", "NOT_CLAIMED", "NOT_RUN"):
        assert fragment in joined, f"the scope limit {fragment!r} was dropped"
    assert "additive only" in match["relation_to_the_earlier_blocked_record"]

    investigation = followup["lifecycle_instability_investigation"]
    assert "empty mapping both when a directory is missing" in investigation["what_the_published_record_could_not_say"]
    assert "labelled as an inference" in investigation["reasoning_kept_separate_from_evidence"]
    assert investigation["classification"].startswith("runner or external filesystem event")
    assert "did not reproduce" in investigation["classification"]
    assert "403" in investigation["repeatability_limit"] and "REL-13 stays OPEN" in investigation["repeatability_limit"]
    protections = investigation["protections_reviewed_and_left_untouched"]
    assert len(protections) >= 11 and all("unchanged" in item or "nothing added" in item
                                         or "still fails" in item for item in protections.values())
    assert "attempt in (1, 2)" in protections["exactly_one_bounded_launch_retry"]
    assert "install_dir_emptied" in protections["exit_code_alone_is_not_uninstall_success"]
    diagnostics = investigation["diagnostics_added"]
    assert "diagnostics.uninstall_forensics" in diagnostics["location"]
    assert len(diagnostics["sample_moments"]) == 6 and len(diagnostics["cases_it_distinguishes"]) == 6
    assert "bound()" in diagnostics["bounds_and_redaction"] and "64 MB" in diagnostics["bounds_and_redaction"]
    assert "never named as a cause" in diagnostics["explicitly_not_collected"]
    assert "v1" in diagnostics["schema"] and "additive" in diagnostics["schema"]
    assert "attempt 2:" in investigation["one_regression_the_work_found"]

    validation = followup["correction_validation"]
    battery = validation["mutation_battery"]
    assert battery["caught"] == battery["attempted"] and battery["survived"] == 0
    assert battery["first_run"], "the coverage defects this battery found stay on the record"
    assert "evidence of detection, not a complete proof" in battery["honest_limit"]
    assert len(validation["contract_guards_added"]) >= 4

    local = followup["local_verification"]
    for claim in (local["focused"], local["release_relevant_scope"]):
        # arithmetic over the whole summary line, rather than the earlier guard's "equal unless the
        # environmental cause is named" rule: a skip and a failure are both legitimate shortfalls from
        # `collected`, and a count that adds up cannot be quietly rounded into looking clean
        counts = re.search(r"(\d+) collected, (\d+) passed, (\d+) failed, (\d+) errors?, (\d+) skipped", claim)
        assert counts, "the record must state a full pytest summary shape, not only its conclusions"
        collected, passed, failed, errors, skipped = (int(group) for group in counts.groups())
        assert collected == passed + failed + errors + skipped, (
            f"{collected} collected does not equal {passed}+{failed}+{errors}+{skipped}; the counts were edited")
    assert "libGL.so.1" in local["release_relevant_scope"] and "kept as failures" in local["release_relevant_scope"]
    assert "5375" in local["lint"] and "not lint-clean" in local["lint"]
    assert "measured on the working tree that became" in local["tree"]

    final = followup["final_tip_gates"]
    assert re.fullmatch(r"[0-9a-f]{40}", final["code_sha"]), final["code_sha"]
    assert final["source_release_gate"]["conclusion"] == "success" == final["windows_release_validation"]["conclusion"]
    assert "cannot record its own gate outcome" in final["records_tip"]

    separations = followup["separations_preserved"]
    assert separations["synthetic_workbook"] == "AUTOMATED_TEST_ONLY_NOT_REAL_DDR_ACCEPTANCE"
    assert "skipped by policy" in separations["bundle_smoke"]
    assert followup["verdict"]["statement"] == "RELEASE-ENGINEERING PASS WITH EXPLICIT EXTERNAL ACCEPTANCE PENDING"
    assert "NOT_ESTABLISHED" in match["what_it_does_not_change"][3]


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
                                                     "sentinel", "never simulated",
                                                     "deleted_files_in_install_dir",
                                                     "was present after install (installed_files) and is absent now",
                                                     "one bounded retry", "uninstall_launch_recovered"]),
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
    normalized = " ".join(text.split())
    assert "never executes a downloaded binary" in normalized
    assert "INDEPENDENT_ARTIFACT_REVERIFICATION=BLOCKED" in normalized, (
        "a retrieval failure caused by the network path must be recorded as blocked, not as a pass")
    assert "*.blob.core.windows.net" in normalized, "the runbook must name the host that blocks the download"


def test_the_runbook_states_the_read_bound_and_the_no_rerun_procedure():
    """The operator-facing contract is documentation, so it drifts silently unless it is pinned.

    A reader of the runbook has to learn three things from it: how much of a log the gate actually
    inspected, that a diagnostic error cannot change a verdict, and what to do when a run cannot be
    re-executed.  These are the sentences that carry them.
    """
    runbook = _read(ROOT / "packaging" / "WINDOWS_RELEASE_ACCEPTANCE.md")
    assert "Bounded, handle-anchored log reads (M42.8; confined to a handle in M42.9)" in runbook
    assert "race-safe" not in runbook, ("M42.8's heading promised more than its code delivered -- a name checked "
                                        "and then opened is not race-safe -- and a runbook that keeps the sentence "
                                        "after the reasoning changed teaches the wrong contract")
    assert "LOG_TAIL_BYTES = 512 KiB" in runbook, "the cap has to be stated as a number, not as 'bounded'"
    assert "before the file is opened rather than clamped" in runbook, ("the ceiling is operator-visible, and a "
                                                                        "clamped override would misreport the read")
    for anchor in ("O_NOFOLLOW", "S_ISREG", "GetFileInformationByHandle", "GetFinalPathNameByHandleW",
                   "GetFileType", "use-then-verify"):
        assert anchor in runbook, f"{anchor} is what the guarantee actually rests on, so the runbook names it"
    assert "*not* claim, on either platform" in runbook and "never counted as native junction coverage" in runbook, (
        "the residual belongs in the operator's document, not only in the code comments")
    assert "older content was not inspected" in runbook
    assert "skipped_unsafe_path" in runbook
    assert "permitted_root=work_root" in runbook, "the boundary has to name the root it is bounded to"
    assert "sampler_failed" in runbook and "changes no verdict" in runbook
    assert "Reading a lifecycle failure without a rerun" in runbook
    assert "403 Resource not accessible by integration" in runbook, (
        "the rerun refusal is the reason the procedure exists; omitting it implies an access the gate does not have")
    assert "emptied by a real uninstall" in runbook and "install tree removed" in runbook, (
        "the five shapes the record has to distinguish are the point of the procedure")


def test_m42_8_followup_records_the_handoff_without_promoting_anything():
    """The hand-off key has to keep every external position where it found it, and its numbers have to add up.

    A follow-up that improves diagnostics is only honest if REL-13 stays open, if a metadata listing is not
    written up as a byte verification, if a blocked push is recorded as blocked rather than as green, and if
    the counts it quotes satisfy the collection identity.  The shape is checked, not the size of the test
    population, because a guard must not pin a number that adding the guard itself changes.
    """
    payload = json.loads(M425_CHECKPOINT.read_text(encoding="utf-8"))
    keys = list(payload)
    assert keys[-1] == "m42_9_followup", (
        "the record is still extended additively: M42.9 appended its own follow-up as the last key rather than "
        "inserting one, which is what rewriting what earlier guards pinned would have looked like")
    assert keys[-2] == "m42_8_followup", "the M42.8 record keeps its place in the order, directly before it"
    key = payload["m42_8_followup"]
    assert key["mission"] == "M42.8" and key["recorded_on"] == "2026-10-11"
    assert payload["m42_6_release_closure"]["independent_artifact_reverification"]["verdict"] == "BLOCKED"
    assert payload["m42_7_followup"]["independent_artifact_match"]["status"] == "MATCH_REPORTED_BY_EXTERNAL_REVIEWER"

    contract = key["bounded_read_contract"]
    assert "512 * 1024" in contract["limit"] and "524288" in contract["limit"], ("the bound is a number in the "
                                                                                "record, not the adjective 'bounded'")
    for state in ("complete", "truncated", "empty", "absent", "unreadable", "skipped_unsafe_path"):
        assert state in contract["states"], f"the published state vocabulary lost {state}"
    assert "older content was not inspected" in contract["elision_marker"]
    assert "400" in contract["publication_bound"], "the read bound and the publish bound are two different limits"

    assert len(key["preserved_m42_7_protections"]["list"]) == 11, "every M42.7 protection is named, or none is"
    assert "drillmaster-installer-lifecycle/v1" in key["preserved_m42_7_protections"]["schema"]
    assert "no version bump" in key["preserved_m42_7_protections"]["schema"]

    handoff = key["external_acceptance_handoff"]
    assert handoff["REL-13"]["status"] == "OPEN", "forensics improve diagnosability, not the root cause"
    assert "403 Resource not accessible by integration" in handoff["REL-13"]["rerun_boundary"]
    assert handoff["REL-04"]["byte_verification"].startswith("NOT_VERIFIED")
    positions = json.dumps(handoff["unchanged_external_positions"])
    for claim in ("UNKNOWN", "NOT_CLAIMED", "NOT_ESTABLISHED", "NOT_RUN", "AUTOMATED_TEST_ONLY_NOT_REAL_DDR_ACCEPTANCE"):
        assert claim in positions, f"an unchanged external position was dropped: {claim}"

    for field in ("focused", "release_relevant_scope"):
        text = key["local_verification"][field]
        for collected, passed, failed, errors, skipped in re.findall(
                r"(\d+) collected, (\d+) passed, (\d+) failed, (\d+) errors?, (\d+) skipped", text):
            assert int(collected) == int(passed) + int(failed) + int(errors) + int(skipped), \
                f"{field} does not add up: {text[:90]}"
        else:
            assert re.search(r"\d+ collected", text), f"{field} lost its measurement"

    publication = key["publication_and_gates"]
    assert re.fullmatch(r"[0-9a-f]{40}", publication["code_sha"]) and re.fullmatch(r"[0-9a-f]{40}",
                                                                                   publication["incoming_sha"])
    # the first published run failed, and the record says so: a follow-up may fix a defect, never bury the run
    assert publication["gates_on_the_code_sha"].startswith("FAILURE"), (
        "the failed exact-SHA gate has to be recorded as a failure, not as history that no longer matters")
    assert "skipped, not failed" in publication["gates_on_the_code_sha"], "the cascade has to be described exactly"
    assert "was weakened to obtain green" in publication["response"], "the fix must state what it did not touch"
    assert "cannot cite its own run" in publication["this_records_commit"], (
        "a record may not claim a gate result for the commit that carries it")
    assert "bypassed" in publication["credential_episode"], "the blocked window is part of the record"
    assert publication["no_post_gate_commit"], "re-verification on a new tip is a rule, not an aspiration"


def test_m42_9_followup_records_the_confinement_correction_without_promoting_anything():
    """The M42.9 key has to correct a claim, keep the record it corrects intact, and promote nothing.

    Three failure modes are worth a guard rather than a review comment: a follow-up that quietly rewrites
    the sentence it is correcting; a follow-up that reports the mutation battery as more successful than the
    per-entry results support; and a follow-up that lets `UNKNOWN`, `NOT_VERIFIED`, `NOT_RUN` or an open REL
    soften while everyone is looking at the reader.  Numbers are checked for self-consistency, never pinned
    to a value this guard itself would change.
    """
    payload = json.loads(M425_CHECKPOINT.read_text(encoding="utf-8"))
    assert list(payload)[-1] == "m42_9_followup", ("the record is extended additively; inserting a key would "
                                                   "rewrite what earlier guards already pinned")
    key = payload["m42_9_followup"]
    assert key["mission"] == "M42.9" and key["recorded_on"] == "2026-10-12"

    prior = payload["m42_8_followup"]
    assert "race-safe" in json.dumps(prior), ("M42.8's own words are preserved verbatim, including the phrase "
                                              "this mission retires; a corrected record that rewrites its "
                                              "predecessor proves nothing about when either was true")
    assert prior["publication_and_gates"]["gates_on_the_code_sha"].startswith("FAILURE"), (
        "the failed run stays recorded as the reason the fix exists")
    assert prior["external_acceptance_handoff"]["REL-13"]["status"] == "OPEN"

    for section in ("correction_of_the_m42_8_race_safe_claim", "handle_anchored_confinement",
                    "platform_limits_stated_verbatim", "tail_bound_ceiling", "window_boundary_rule",
                    "digest_and_hash_plumbing", "preserved_protections", "tests_added",
                    "correction_validation", "local_verification", "publication_and_gates",
                    "external_positions_unchanged", "verdict"):
        assert section in key, f"the record lost the section {section}"

    text = json.dumps(key)
    for mechanism in ("O_NOFOLLOW", "dir_fd", "S_ISREG", "O_NONBLOCK", "GetFinalPathNameByHandleW",
                      "GetFileInformationByHandle", "reparse"):
        assert mechanism in text, f"the record stopped naming {mechanism}, which is what the guarantee rests on"
    verdict = json.dumps(key["verdict"]).lower()
    assert "narrows" in json.dumps(key["platform_limits_stated_verbatim"]).lower(), (
        "the residual has to be in the record, not only in a code comment")
    assert "not_established" in key["verdict"] and "no windows-native junction" in verdict, (
        "a verdict that establishes everything, or that stops naming the platform it could not exercise, is a "
        "verdict to distrust")
    assert "524289" in json.dumps(key["tail_bound_ceiling"]), "the ceiling is a number in the record"
    assert "ValueError" in json.dumps(key["tail_bound_ceiling"]), "oversized overrides are refused, not clamped"
    assert "dropped_partial_first_line=false" in json.dumps(key["window_boundary_rule"])
    assert "grew_during_read" in json.dumps(key["window_boundary_rule"])
    assert "replaced_before_open" in json.dumps(key["digest_and_hash_plumbing"])
    assert "sha256_stream" in json.dumps(key["digest_and_hash_plumbing"]), (
        "the shared helper is the reason there is still exactly one digest implementation")
    assert "simulated" in json.dumps(key["platform_limits_stated_verbatim"])

    battery = key["correction_validation"]["mutation_battery"]
    assert len(battery["per_entry"]) >= 15, "one entry per mutation class is the minimum the mission named"
    outcomes = {item["outcome"] for item in battery["per_entry"]}
    assert outcomes <= {"caught", "caught-by-timeout", "survived"}, outcomes
    survivors = sum(1 for item in battery["per_entry"] if item["outcome"] == "survived")
    assert battery["result"].count(f"{survivors} survived") == 1, (
        f"the headline says {battery['result']!r} but the entries list {survivors} survivors")
    assert "27-of-27" in battery["not_reused"] or "not cited" in battery["not_reused"]

    for field in ("focused", "release_relevant_scope", "source_gate_suite"):
        passage = json.dumps(key["local_verification"][field])
        for collected, passed, failed, errors, skipped in re.findall(
                r"(\d+) collected, (\d+) passed, (\d+) failed, (\d+) errors?, (\d+) skipped", passage):
            assert int(collected) == int(passed) + int(failed) + int(errors) + int(skipped), \
                f"{field} does not add up: {passage[:120]}"
        else:
            assert re.search(r"\d+ collected", passage), f"{field} lost its measurement"

    positions = json.dumps(key["external_positions_unchanged"])
    for claim in ("UNKNOWN", "NOT_VERIFIED", "NOT_RUN", "NOT_CLAIMED", "NOT_ESTABLISHED", "OPEN",
                  "AUTOMATED_TEST_ONLY_NOT_REAL_DDR_ACCEPTANCE"):
        assert claim in positions, f"an unchanged external position was dropped: {claim}"
    assert "cannot attest" in json.dumps(key["publication_and_gates"]), (
        "a commit may not cite the run that will be triggered by pushing it")
    assert key["verdict"]["not_established"], "a verdict that establishes everything is a verdict to distrust"


def test_windows_gate_announces_a_run_that_named_no_failing_test(workflow_text):
    """A red step that publishes nothing is the failure mode these diagnostics exist to remove.

    pytest writes its JUnit XML only when it reaches the end of the run, so an interrupted, aborted or
    refused run leaves no test identity for the parser to annotate; and pwsh 7.3+ turns a line on a native
    command's stderr into a terminating error under the runner's ``Stop`` preference, which is one way a run
    gets interrupted.  The step therefore captures its own output, hands the exit code and the log to the
    tested parser, and carries the same two preference guards the build step uses -- while still propagating
    pytest's exit code, so the diagnostics can neither redden a green run nor green a red one.
    """
    block = _step_block(workflow_text, "Windows database, import, auth and packaging regression suite")
    assert "2>&1 | Tee-Object -FilePath $testLog" in block, (
        "the run must be captured, because the log is the only witness a report-less abort leaves")
    assert '--pytest-exit $pytestExit' in block, "the parser has to be told the exit code it must explain"
    assert "--pytest-log" in block
    assert '$ErrorActionPreference = "Continue"' in block and \
        "$PSNativeCommandUseErrorActionPreference = $false" in block, (
        "a redirected native pipeline under the Stop preference aborts the step on native stderr")
    assert block.index('$ErrorActionPreference = "Continue"') < block.index("2>&1 | Tee-Object"), (
        "the preference must be relaxed before the pipeline that can trip on it")
    assert block.index("2>&1 | Tee-Object") < block.index("$pytestExit = $LASTEXITCODE"), (
        "the exit code must be read straight after the pipeline, before anything else can overwrite it")
    calls = [line for line in block.splitlines() if r"packaging\junit_report.py --junit" in line]
    assert len(calls) == 1, "the regression step must call the tested parser exactly once"
    assert "--pytest-exit $pytestExit" in calls[0] and "--pytest-log \"$testLog\"" in calls[0], (
        "the exit code and the captured log have to reach the parser on its own command line")
    assert "'windows-regressions.log'" in block, "the captured log belongs to the disposable runner temp root"
    upload = workflow_text[workflow_text.index("- name: Upload Windows evidence artifacts"):]
    assert "$testLog" not in upload and "windows-regressions.log" not in upload, (
        "the raw pytest transcript stays in the runner temp root: it is quoted, bounded and redacted into "
        "an annotation, never published as an artifact")


def test_junit_parser_explains_a_report_that_explains_nothing():
    """The parser, not the YAML, owns the wording -- so the guarantee is testable on any platform."""
    source = (ROOT / "packaging" / "junit_report.py").read_text(encoding="utf-8")
    for fragment in ("def describe_abort(", "--pytest-exit", "--pytest-log", "no failing test to name",
                     "def _bounded(", "def _log_parts("):
        assert fragment in source, f"junit_report lost the abort-diagnostic piece {fragment!r}"
    assert source.index("def describe_abort(") < source.index("def emit("), (
        "the explanation is composed before anything is written to the workflow's stdout")


def test_windows_gate_arms_the_crash_breadcrumb_and_the_hook_stays_opt_in(workflow_text, monkeypatch, capfd):
    """The active test's identity must survive a death that leaves no JUnit report.

    Three consecutive Windows runs died inside pytest's report pipeline with stacks naming no test, so
    the suite writes each test's nodeid unbuffered at its start and the parser quotes the last one.
    The producer half is opt-in: armed only by this step, every other run stays byte-for-byte silent.
    """
    block = _step_block(workflow_text, "Windows database, import, auth and packaging regression suite")
    assert "$env:DRILLMASTER_CRASH_BREADCRUMB = '1'" in block, (
        "the regression step must arm the breadcrumb before pytest starts")
    assert block.index("DRILLMASTER_CRASH_BREADCRUMB") < block.index("2>&1 | Tee-Object"), (
        "the breadcrumb must be armed before the pipeline whose log it has to land in")

    spec = importlib.util.spec_from_file_location(
        "drillmaster_tests_conftest", ROOT / "tests" / "conftest.py")
    conftest = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(conftest)

    monkeypatch.delenv("DRILLMASTER_CRASH_BREADCRUMB", raising=False)
    conftest.pytest_runtest_logstart("tests/test_x.py::test_silent", ("tests/test_x.py", 1, "test_silent"))
    assert capfd.readouterr().err == "", "without the opt-in the hook must write nothing"

    monkeypatch.setenv("DRILLMASTER_CRASH_BREADCRUMB", "1")
    conftest.pytest_runtest_logstart("tests/test_x.py::test_named", ("tests/test_x.py", 2, "test_named"))
    written = capfd.readouterr().err
    # capfd sees file-descriptor writes; a buffered print would not be here to be captured after a crash.
    assert written == "DRILLMASTER-TEST-START tests/test_x.py::test_named\n", written
