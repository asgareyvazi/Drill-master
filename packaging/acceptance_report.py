"""Generate an explicit, machine-readable Windows release acceptance report.

This report describes repository automation only.  It deliberately records
interactive/operator and real-input acceptance as NOT_RUN; synthetic workbook
coverage is not real DDR/PDF/MinerU acceptance.

Every claim it makes is re-derived from files in the release directory: artifact
hashes are recomputed here (streaming, not whole-file reads), the Inno Setup
identity is re-validated rather than copied, and lifecycle or signing evidence is
reported as NOT_RUN when the corresponding build step produced no report.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

_PACKAGING_DIR = Path(__file__).resolve().parent
if str(_PACKAGING_DIR) not in sys.path:
    sys.path.insert(0, str(_PACKAGING_DIR))

from release_metadata import (  # noqa: E402  (path bootstrap above is required)
    SCHEMA as METADATA_SCHEMA,
    SIGNING_ABSENCE_VOCABULARY,
    SIGNING_SCHEMA,
    VERIFIED_IDENTITY_SOURCES,
    sha256_file,
    validate_document,
    validate_identity_source,
    validate_signing_document,
    validate_tool_version,
)

SMOKE_FIELDS = ("exit_code", "log_generated", "secret_leak_detected", "smoke_timeout", "smoke_execution_error")
REPORT_SCHEMA = "drillmaster-windows-acceptance/v2"
REQUIRED_REPORT_FIELDS = (
    "source_sha", "app_version", "platform", "python_version", "pip_version", "pyinstaller_version",
    "innosetup_package_version", "innosetup_compiler_file_version", "innosetup_version_source",
    "installer_filename", "installer_sha256", "installer_size_bytes", "portable_zip_filename",
    "portable_zip_sha256", "portable_zip_size_bytes", "windows_regression_passed",
    "windows_regression_failed", "windows_regression_errors", "windows_regression_skipped",
    "skipped_tests", "frozen_smoke_status", "frozen_smoke_exit_code", "secret_leak_check",
    "installer_compilation_status", "installed_lifecycle_status", "signing_status",
    "ci_workflow", "ci_run_id", "ci_run_url", "ci_branch", "external_acceptance",
    "artifact_independent_reverification",
)
STATUS_VOCABULARY = {"PASS", "PASS_WITH_SKIPS", "FAIL", "NOT_RUN", "BLOCKED", "UNKNOWN", "UNSIGNED",
                     "NOT_VERIFIED", "SEPARATE_EXACT_SHA_WORKFLOW_REQUIRED"}
CI_RUN_ID_PATTERN = re.compile(r"^\d+$")


class ReportError(ValueError):
    """A release claim that the available evidence does not support."""


def read_artifact(root: Path, entry: dict) -> dict:
    """Require the recorded artifact to exist and to match its recorded SHA-256.

    The report must not claim packaging success from a manifest alone: the file is
    re-hashed here by streaming the file in fixed blocks, so a missing or altered
    artifact is a hard failure without loading a ~300 MB executable into memory.
    """
    filename = str(entry["filename"])
    path = root / filename.replace("/", os.sep)
    if not path.is_file():
        raise ReportError(f"release artifact missing: {filename}")
    actual = sha256_file(path)
    if actual != entry.get("sha256"):
        raise ReportError(f"release artifact hash mismatch: {filename}")
    size = path.stat().st_size
    recorded_size = entry.get("size_bytes")
    if recorded_size is not None and int(recorded_size) != size:
        raise ReportError(f"release artifact size mismatch: {filename} (manifest {recorded_size}, observed {size})")
    return {"filename": filename, "sha256": actual, "size_bytes": size, "hash_verified": True}


def read_smoke_evidence(path: Path) -> dict:
    """Bind the frozen-executable claim to the log written by the smoke run."""
    if not path.is_file():
        raise ReportError(f"package smoke evidence missing: {path.name}")
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() in SMOKE_FIELDS:
            fields.setdefault(key.strip(), value.strip())
    if fields.get("smoke_timeout") or fields.get("smoke_execution_error"):
        raise ReportError("package smoke evidence reports a timeout or execution error")
    if fields.get("exit_code") != "0":
        raise ReportError("package smoke evidence does not record exit_code=0")
    if fields.get("log_generated") != "true":
        raise ReportError("package smoke evidence shows the frozen application wrote no log")
    if fields.get("secret_leak_detected") != "false":
        raise ReportError("package smoke evidence reports a secret leak")
    return {"log": path.name, "exit_code": 0, "log_generated": True, "secret_leak_detected": False}


def read_innosetup_identity(build_tools: dict, *, installer_present: bool,
                            expected_version: str) -> dict:
    """Re-validate the toolchain identity instead of copying it from the manifest."""
    identity = {
        "innosetup_package_version": validate_tool_version(
            build_tools.get("innosetup_package_version"),
            field="innosetup_package_version",
            artifact_present=installer_present,
        ),
        "innosetup_compiler_file_version": str(
            build_tools.get("innosetup_compiler_file_version") or "UNAVAILABLE"
        ).strip(),
        "innosetup_version_source": validate_identity_source(
            build_tools.get("innosetup_version_source"), artifact_present=installer_present
        ),
        "innosetup_identity_verified": bool(build_tools.get("innosetup_identity_verified")),
    }
    if installer_present:
        if identity["innosetup_identity_verified"] and (
            identity["innosetup_version_source"] not in VERIFIED_IDENTITY_SOURCES
        ):
            raise ReportError(
                "release metadata claims a verified Inno Setup identity while recording it as "
                f"{identity['innosetup_version_source']!r}; only "
                + " / ".join(sorted(VERIFIED_IDENTITY_SOURCES)) + " can verify one"
            )
        if not identity["innosetup_identity_verified"]:
            raise ReportError(
                "release metadata did not verify the Inno Setup identity against the installed "
                f"package (source={identity['innosetup_version_source']!r})"
            )
        if expected_version:
            expected = validate_tool_version(expected_version, field="expected Inno Setup version",
                                             artifact_present=True)
            if identity["innosetup_package_version"] != expected:
                raise ReportError(
                    "Inno Setup identity disagreement: the manifest records "
                    f"{identity['innosetup_package_version']!r} while the build requested {expected!r}"
                )
    return identity


def read_lifecycle_evidence(path: Path | None, *, required: bool) -> dict:
    """Fold the installed-application lifecycle report in, or say truthfully that it did not run."""
    absent = {"status": "NOT_RUN",
              "reason": "no installer-lifecycle.json was produced by the build; the packaged "
                        "bundle smoke covers the portable tree, not an installed application",
              "evidence_file": None}
    if path is None or not path.is_file():
        if required:
            raise ReportError("installed-application lifecycle evidence is required but missing")
        return absent
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError(f"installer lifecycle evidence unreadable: {exc}") from exc
    status = str(payload.get("status", "UNKNOWN")).upper()
    if status not in STATUS_VOCABULARY:
        raise ReportError(f"installer lifecycle reported an unknown status: {status!r}")
    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ReportError("installer lifecycle evidence lists no steps")
    if status == "PASS":
        failed = [step.get("name") for step in steps if str(step.get("status", "")).upper() != "PASS"]
        if failed:
            raise ReportError(f"installer lifecycle marked PASS with non-passing steps: {failed}")
        if not payload.get("installer_hash_verified"):
            raise ReportError(
                "installer lifecycle claims PASS without having verified the hash of the installer it executed"
            )
    return {
        "status": status,
        "steps": steps,
        "evidence_file": path.name,
        "installer_verified": bool(payload.get("installer_hash_verified")),
        "installer_sha256": str(payload.get("installer_sha256") or ""),
        "installer_filename": str(payload.get("installer_filename") or ""),
        "signing": payload.get("signing") or {},
        "diagnostics": payload.get("diagnostics") or {},
    }


SIGNING_FILE_EVIDENCE_FIELDS = (
    "filename", "status", "raw_status", "raw_status_recognized", "status_message", "signer",
    "provenance", "sha256", "container_archive", "container_archive_sha256", "container_member",
    "signature_bearing",
)


def read_signing_evidence(path: Path | None, *, required: bool = False, binding: dict | None = None) -> dict:
    """Report signature status as observed; never infer it from the build succeeding.

    Three situations used to be blurred together here and are now separated:

    * no evidence document at all -- ``NOT_VERIFIED`` when the workflow did not declare signing
      evidence mandatory, a hard error when it did (``required``).  ``NOT_VERIFIED`` is a report
      state describing an absent record; it is deliberately not part of the Authenticode
      vocabulary and never appears as a per-file or aggregate status;
    * a record that cannot be trusted -- wrong schema, a field outside the contract, a duplicate
      row, an unbounded diagnostic, or an aggregate the per-file findings do not support.  That is
      an evidence-integrity failure and raises, because silently re-deriving a second answer here
      would let the report and the generator disagree about what Windows said;
    * a valid record, whose aggregate is validated rather than recomputed by a rival rule.

    ``binding`` ties the record to the exact bytes this report verified: the manifest it was
    derived from, the source SHA, and the installer and portable-archive digests that were
    recomputed a moment ago.  Without it, a stale or copied record would be accepted.
    """
    if path is None or not path.is_file():
        if required:
            raise ReportError("signature verification evidence is required but missing; "
                              "a missing signing record is not evidence of an acceptable unsigned build")
        # The only report-level state this block can hold, and the only place it is written:
        # it says "no record exists", never "Windows said something".
        return {"status": next(iter(SIGNING_ABSENCE_VOCABULARY)),
                "reason": "no signature verification step ran for this artifact set",
                "schema": None, "method": None, "policy": None, "harness": {},
                "files": [], "examined_count": 0, "archive_count": 0,
                "signing_configured_in_build": False, "credentials_available": False,
                "prerequisite": "", "artifact_binding": "NOT_AVAILABLE"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError(f"signing evidence unreadable or malformed: {exc}") from exc
    try:
        validate_signing_document(payload)
    except ValueError as exc:
        raise ReportError(f"signing evidence is not a valid {SIGNING_SCHEMA} document: {exc}") from exc
    files = payload["files"]
    status = str(payload["status"])
    if binding and status != "NOT_RUN":
        declared = str(payload.get("release_metadata_sha256") or "")
        if declared != str(binding.get("release_metadata_sha256") or ""):
            raise ReportError(
                "signing evidence is not bound to the release metadata this report verified: it "
                f"records manifest digest {declared[:16] or 'nothing'} while the verified manifest is "
                f"{str(binding.get('release_metadata_sha256') or '')[:16]}"
            )
        recorded_sha = str(payload.get("source_sha") or "")
        if recorded_sha != str(binding.get("source_sha") or ""):
            raise ReportError(
                f"signing evidence was produced for source {recorded_sha[:12] or 'nothing'} but this "
                f"report describes {str(binding.get('source_sha') or '')[:12]}; a signature record from "
                "another run is not evidence about these bytes"
            )
        rows = {str(item["filename"]).lower(): item for item in files}
        bundle_name = str(binding.get("bundle_filename") or "").lower()
        installer_name = str(binding.get("installer_filename") or "").lower()
        installer_row = rows.get(installer_name)
        if installer_row is None:
            raise ReportError(f"signing evidence does not record the shipped installer "
                              f"{binding.get('installer_filename')!r}; the file the release depends on was "
                              "never examined")
        if installer_row["sha256"] != str(binding.get("installer_sha256") or ""):
            raise ReportError(
                f"signing evidence for {binding.get('installer_filename')} hashes a different file than "
                "the release artifact this report verified; the record is stale"
            )
        for item in files:
            if not item.get("container_archive"):
                continue
            if str(item["container_archive"]).lower() != bundle_name:
                raise ReportError(f"signing evidence binds {item['filename']} to archive "
                                  f"{item['container_archive']!r}, not to the published {bundle_name}")
            if item["container_archive_sha256"] != str(binding.get("bundle_sha256") or ""):
                raise ReportError(
                    f"signing evidence binds {item['filename']} to archive bytes this report did not verify"
                )
        if bundle_name and not any(str(item.get("container_archive") or "").lower() == bundle_name
                                   for item in files):
            raise ReportError(
                f"signing evidence never examines the executable shipped inside {bundle_name}; a record "
                "that skips the packaged application cannot support a claim about the shipped build"
            )
    retained = [{key: item[key] for key in SIGNING_FILE_EVIDENCE_FIELDS if key in item} for item in files]
    # The aggregate is taken as published, because validate_signing_document above already folded
    # the per-file rows with the one shared rule and refused a record whose files say otherwise.
    # Re-deriving it here with a second expression of the same rule is what used to drift.
    return {"status": status, "schema": payload["schema"], "method": payload["method"],
            "policy": payload["policy"], "harness": dict(payload.get("harness") or {}),
            "reason": str(payload.get("reason") or ""), "files": retained,
            "examined_count": payload["examined_count"], "archive_count": payload["archive_count"],
            "signing_configured_in_build": payload["signing_configured_in_build"],
            "credentials_available": payload["credentials_available"],
            "credential_environment_variables": list(payload.get("credential_environment_variables") or []),
            "prerequisite": payload.get("prerequisite", ""),
            "release_metadata_sha256": str(payload.get("release_metadata_sha256") or ""),
            "source_sha": str(payload.get("source_sha") or ""),
            "artifact_binding": "VERIFIED" if binding else "NOT_CHECKED"}


def _read_junit(junit_path: Path) -> dict:
    cases = ET.parse(junit_path).findall(".//testcase")
    if not cases:
        raise ReportError("JUnit report contains no executed test cases")
    failures = errors = skipped = passed = 0
    skipped_tests = []
    for case in cases:
        failure, error, skip = case.find("failure"), case.find("error"), case.find("skipped")
        if failure is not None:
            failures += 1
        elif error is not None:
            errors += 1
        elif skip is not None:
            skipped += 1
            skipped_tests.append({
                "test": f"{case.get('classname', '')}.{case.get('name', '')}",
                "reason": skip.get("message", ""),
            })
        else:
            passed += 1
    if failures or errors:
        raise ReportError(f"JUnit suite did not pass: failures={failures}, errors={errors}")
    return {"collected": len(cases), "passed": passed, "skipped": skipped,
            "failed": failures, "errors": errors, "skipped_tests": skipped_tests}


def _read_ci_identity(ci: dict, source_sha: str) -> dict:
    """Validate the CI identity the workflow supplies; never fabricate one here."""
    provided = {key: str(ci.get(key, "")).strip() for key in ("workflow", "run_id", "run_url", "branch")}
    if not any(provided.values()):
        return {"workflow": "NOT_PROVIDED", "run_id": "NOT_PROVIDED", "run_url": "NOT_PROVIDED",
                "branch": "NOT_PROVIDED",
                "note": "CI identity is supplied by the workflow at generation time; it is never committed to source."}
    missing = [key for key, value in provided.items() if not value]
    if missing:
        raise ReportError(f"CI identity is incomplete; missing: {', '.join(missing)}")
    if not CI_RUN_ID_PATTERN.match(provided["run_id"]):
        raise ReportError("CI run id must be a numeric GitHub Actions run id")
    if not provided["run_url"].endswith(f"/actions/runs/{provided['run_id']}"):
        raise ReportError("CI run URL must end with the recorded run id")
    return {"workflow": provided["workflow"], "run_id": provided["run_id"],
            "run_url": provided["run_url"], "branch": provided["branch"],
            "note": "CI identity is supplied by the workflow at generation time; it is never committed to source."}


def build_report(*, metadata_path: Path, junit_path: Path, source_sha: str, ci: dict | None = None,
                 expected_innosetup_version: str = "", lifecycle_report_path: Path | None = None,
                 require_lifecycle: bool = False, signing_report_path: Path | None = None,
                 require_signing: bool = False) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha or ""):
        raise ReportError("source SHA must be a full lowercase commit hash")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError(f"release metadata unreadable or malformed: {exc}") from exc
    try:
        validate_document(metadata)
    except ValueError as exc:
        schema = metadata.get("schema") if isinstance(metadata, dict) else None
        if schema is not None and schema != METADATA_SCHEMA:
            raise ReportError(
                f"release metadata must use {METADATA_SCHEMA}; older schemas recorded only an "
                "unverified ISCC file version and cannot support a toolchain claim"
            ) from exc
        raise ReportError(f"release metadata violates its published contract: {exc}") from exc
    if metadata.get("git_sha") != source_sha:
        raise ReportError("release metadata SHA does not match the requested source SHA")

    suite = _read_junit(junit_path)
    release_root = metadata_path.parent
    artifacts = {Path(str(item["filename"])).name: item for item in metadata.get("artifacts", [])}
    bundle = next((name for name in artifacts if name.lower().endswith(".zip")), None)
    installer = next((name for name in artifacts if name.lower().endswith("-setup.exe")), None)
    if not bundle or not installer:
        raise ReportError("release metadata must evidence both portable ZIP and compiled installer")
    bundle_artifact = read_artifact(release_root, artifacts[bundle])
    installer_artifact = read_artifact(release_root, artifacts[installer])
    smoke_evidence = read_smoke_evidence(release_root / "package-smoke.log")
    identity = read_innosetup_identity(metadata["build_tools"], installer_present=True,
                                       expected_version=expected_innosetup_version)
    lifecycle = read_lifecycle_evidence(lifecycle_report_path, required=require_lifecycle)
    if lifecycle["status"] == "PASS":
        # The lifecycle must have hashed the same bytes this report just hashed.
        if lifecycle["installer_filename"] != installer_artifact["filename"] or (
            lifecycle["installer_sha256"] and lifecycle["installer_sha256"] != installer_artifact["sha256"]
        ):
            raise ReportError(
                "installed-application lifecycle evidence is not bound to the verified installer: it names "
                f"{lifecycle['installer_filename']!r} "
                f"{(lifecycle['installer_sha256'] or 'no hash')[:16]} while the release artifact is "
                f"{installer_artifact['filename']} {installer_artifact['sha256'][:16]}"
            )
    signing = read_signing_evidence(
        signing_report_path, required=require_signing,
        binding={"release_metadata_sha256": sha256_file(metadata_path), "source_sha": source_sha,
                 "installer_filename": installer_artifact["filename"],
                 "installer_sha256": installer_artifact["sha256"],
                 "bundle_filename": bundle_artifact["filename"],
                 "bundle_sha256": bundle_artifact["sha256"]})
    ci_identity = _read_ci_identity(dict(ci or {}), source_sha)
    external = {
        "interactive_clean_machine_install": "NOT_RUN",
        "interactive_upgrade_and_uninstall_data_retention": "NOT_RUN",
        "real_ddr_excel_operator_acceptance": "NOT_RUN",
        "real_ddr_pdf_acceptance": "NOT_RUN",
        "real_mineru_acceptance": "NOT_RUN",
        "production_database_acceptance": "NOT_RUN",
        "field_validation": "NOT_RUN",
        "operator_business_signoff": "NOT_RUN",
        "synthetic_workbook_scenario": "AUTOMATED_TEST_ONLY_NOT_REAL_DDR_ACCEPTANCE",
    }
    lifecycle_status = str(lifecycle["status"])

    report = {
        "schema": REPORT_SCHEMA,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "identity": {
            "source_sha": source_sha,
            "app_version": metadata["version"],
            "platform": metadata["platform"],
            "python_version": metadata["python"],
            "pip_version": metadata["build_tools"]["pip"],
            "pyinstaller_version": metadata["build_tools"]["pyinstaller"],
            "runner_platform": platform.platform(),
            **identity,
            "installer_filename": installer_artifact["filename"],
            "installer_sha256": installer_artifact["sha256"],
            "installer_size_bytes": installer_artifact["size_bytes"],
            "portable_zip_filename": bundle_artifact["filename"],
            "portable_zip_sha256": bundle_artifact["sha256"],
            "portable_zip_size_bytes": bundle_artifact["size_bytes"],
        },
        "repository_automation": {
            "windows_regression_suite": {
                "status": "PASS_WITH_SKIPS" if suite["skipped"] else "PASS",
                "collected": suite["collected"], "passed": suite["passed"],
                "skipped": suite["skipped"], "failed": suite["failed"], "errors": suite["errors"],
                "skipped_tests": suite["skipped_tests"],
            },
            "portable_bundle_build": {"status": "PASS", **bundle_artifact},
            "frozen_executable_smoke": {"status": "PASS", "mode": "isolated --package-smoke",
                                        "exit_code": smoke_evidence["exit_code"],
                                        "evidence": smoke_evidence},
            "installer_compilation": {"status": "PASS", **installer_artifact,
                                      **{key: identity[key] for key in
                                         ("innosetup_package_version", "innosetup_compiler_file_version",
                                          "innosetup_version_source", "innosetup_identity_verified")}},
            "installed_application_lifecycle": {
                "status": lifecycle_status,
                "scope": "automated silent install/run/uninstall on an ephemeral CI runner",
                "steps": lifecycle.get("steps", []),
                "reason": lifecycle.get("reason", ""),
                "evidence_file": lifecycle.get("evidence_file"),
                "installer_hash_verified": lifecycle.get("installer_verified", False),
                "installer_sha256": lifecycle.get("installer_sha256", ""),
                "bound_to_verified_artifact": bool(
                    lifecycle.get("installer_sha256") == installer_artifact["sha256"]
                    and lifecycle.get("installer_filename") == installer_artifact["filename"]
                ),
                "note": "An automated lifecycle smoke is not interactive clean-machine or operator acceptance.",
            },
            "code_signing": signing,
            "artifact_verification": {
                "status": "PASS",
                "method": "streaming SHA-256 recomputation against release-metadata.json and SHA256SUMS.txt",
                "verified_artifacts": [installer_artifact["filename"], bundle_artifact["filename"]],
                # Four claims are kept apart on purpose: what the build produced, what this
                # report recomputed, what the workflow re-measured on the runner, and what only
                # an operator with the downloaded bytes can confirm.
                "provenance": "built from the pinned source SHA by packaging/build_windows.ps1; digests recomputed "
                              "from the release directory while this report was generated",
                "independent_reverification": "NOT_VERIFIED",
                "operator_verification_path": "recompute Get-FileHash -Algorithm SHA256 for each line of "
                                              "SHA256SUMS.txt after download; a job annotation or CI log is not "
                                              "byte-integrity proof of the artifact you hold",
            },
            "reproducible_build": metadata.get("reproducible_build", {"status": "NOT_CLAIMED"}),
            "source_release_gate": "SEPARATE_EXACT_SHA_WORKFLOW_REQUIRED",
        },
        "ci": ci_identity,
        "external_acceptance": external,
        "status_vocabulary": sorted(STATUS_VOCABULARY),
    }
    # Three outcomes are distinct: the automation passed, a mandatory step did not run, or a
    # step ran and failed.  Collapsing the last two into "did not run" once let a report carry
    # WINDOWS_AUTOMATION_PASS while the installed-application smoke had failed.
    mandatory = {"INSTALLED_LIFECYCLE": lifecycle_status,
                 "FROZEN_SMOKE": str((report["repository_automation"]["frozen_executable_smoke"] or {}).get("status")),
                 "INSTALLER_COMPILATION": str(report["repository_automation"]["installer_compilation"]["status"])}
    blocked = {name: value for name, value in mandatory.items() if value not in {"PASS", "NOT_RUN", "NOT_VERIFIED"}}
    unrun = {name: value for name, value in mandatory.items() if value in {"NOT_RUN", "NOT_VERIFIED"}}
    if blocked:
        verdict = "WINDOWS_AUTOMATION_FAIL"
        detail = "; ".join(f"{name}_{value}" for name, value in sorted(blocked.items()))
    elif unrun:
        verdict = "WINDOWS_AUTOMATION_PASS"
        detail = "; ".join(f"{name}_{value}" for name, value in sorted(unrun.items()))
    else:
        verdict = "WINDOWS_AUTOMATION_PASS"
        detail = "; ".join(f"{name}_PASS" for name in sorted(mandatory))
    report["decision"] = f"{verdict}; {detail}; SOURCE_GATE_AND_EXTERNAL_ACCEPTANCE_REMAIN_SEPARATE"
    report["decision_basis"] = {"mandatory_statuses": mandatory,
                                "blocking": sorted(blocked),
                                "not_run": sorted(unrun),
                                "note": "a signature state is deliberately absent here: whether the release is "
                                        "signed is an owner decision recorded under repository_automation.code_signing"}
    report["identity"]["installed_lifecycle_status"] = lifecycle_status
    report["identity"]["signing_status"] = signing["status"]
    return report


def _flatten_for_verification(report: dict) -> dict:
    """Expose the contract's field names in one flat mapping for validation and tooling.

    Reads are tolerant on purpose: a report that omits evidence must be reported as a
    missing field by :func:`verify_report_fields`, not crash with a KeyError first.
    """
    identity = report.get("identity", {})
    automation = report.get("repository_automation", {})
    suite = automation.get("windows_regression_suite", {})
    smoke = automation.get("frozen_executable_smoke", {})
    signing = automation.get("code_signing", {})
    installer = automation.get("installer_compilation", {})
    return {
        "source_sha": identity.get("source_sha"), "app_version": identity.get("app_version"),
        "platform": identity.get("platform"), "python_version": identity.get("python_version"),
        "pip_version": identity.get("pip_version"), "pyinstaller_version": identity.get("pyinstaller_version"),
        "innosetup_package_version": identity.get("innosetup_package_version"),
        "innosetup_compiler_file_version": identity.get("innosetup_compiler_file_version"),
        "innosetup_version_source": identity.get("innosetup_version_source"),
        "installer_filename": installer.get("filename", identity.get("installer_filename")),
        "installer_sha256": installer.get("sha256", identity.get("installer_sha256")),
        "installer_size_bytes": installer.get("size_bytes", identity.get("installer_size_bytes")),
        "portable_zip_filename": identity.get("portable_zip_filename"),
        "portable_zip_sha256": identity.get("portable_zip_sha256"),
        "portable_zip_size_bytes": identity.get("portable_zip_size_bytes"),
        "windows_regression_passed": suite.get("passed"), "windows_regression_failed": suite.get("failed"),
        "windows_regression_errors": suite.get("errors"), "windows_regression_skipped": suite.get("skipped"),
        "skipped_tests": suite.get("skipped_tests"),
        "frozen_smoke_status": smoke.get("status"), "frozen_smoke_exit_code": smoke.get("exit_code"),
        "secret_leak_check": (smoke.get("evidence") or {}).get("secret_leak_detected"),
        "installer_compilation_status": installer.get("status"),
        "installed_lifecycle_status": identity.get("installed_lifecycle_status",
                                                   automation.get("installed_application_lifecycle", {}).get("status")),
        "signing_status": signing.get("status", identity.get("signing_status")),
        "ci_workflow": report.get("ci", {}).get("workflow"), "ci_run_id": report.get("ci", {}).get("run_id"),
        "ci_run_url": report.get("ci", {}).get("run_url"), "ci_branch": report.get("ci", {}).get("branch"),
        "external_acceptance": report.get("external_acceptance"),
        "artifact_independent_reverification": automation.get("artifact_verification", {}).get(
            "independent_reverification"),
    }


def verify_report_fields(report: dict) -> None:
    """Fail if the report omits a field the release contract requires."""
    flat = _flatten_for_verification(report)
    missing = [field for field in REQUIRED_REPORT_FIELDS if flat.get(field) in (None, "")]
    if missing:
        raise ReportError(f"acceptance report is missing required fields: {', '.join(missing)}")
    for key in ("installer_compilation_status", "frozen_smoke_status", "installed_lifecycle_status",
                "signing_status"):
        value = flat[key]
        if value not in STATUS_VOCABULARY:
            raise ReportError(f"acceptance report field {key} has a status outside the vocabulary: {value!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--junit", required=True, type=Path)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--ci-workflow", default="")
    parser.add_argument("--ci-run-id", default="")
    parser.add_argument("--ci-run-url", default="")
    parser.add_argument("--ci-branch", default="")
    parser.add_argument("--expected-innosetup-version", default="",
                        help="version the build was pinned to; disagreement fails the report")
    parser.add_argument("--lifecycle-report", type=Path,
                        help="installer-lifecycle.json produced by the installed-application smoke")
    parser.add_argument("--require-lifecycle", action="store_true",
                        help="fail when no lifecycle evidence exists (used by the Windows release gate)")
    parser.add_argument("--signing-report", type=Path,
                        help="signing-status.json produced by the signature verification step")
    parser.add_argument("--require-signing", action="store_true",
                        help="fail when no signing evidence exists (used by the Windows release gate)")
    args = parser.parse_args(argv)
    try:
        report = build_report(
            metadata_path=args.metadata, junit_path=args.junit, source_sha=args.source_sha,
            ci={"workflow": args.ci_workflow, "run_id": args.ci_run_id, "run_url": args.ci_run_url,
                "branch": args.ci_branch},
            expected_innosetup_version=args.expected_innosetup_version,
            lifecycle_report_path=args.lifecycle_report, require_lifecycle=args.require_lifecycle,
            signing_report_path=args.signing_report, require_signing=args.require_signing,
        )
        verify_report_fields(report)
    except ReportError as exc:
        # A clean refusal, not a traceback: the message is what an operator reads in the log.
        print(f"acceptance report refused: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Windows acceptance report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
