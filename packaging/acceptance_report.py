"""Generate an explicit, machine-readable Windows release acceptance report.

This report describes repository automation only. It deliberately records
interactive/operator and real-input acceptance as NOT_RUN; synthetic workbook
coverage is not real DDR/PDF/MinerU acceptance.
"""
from __future__ import annotations

import argparse
import json
import platform
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


def build_report(*, metadata_path: Path, junit_path: Path, source_sha: str) -> dict:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("git_sha") != source_sha:
        raise ValueError("release metadata SHA does not match the requested source SHA")

    cases = ET.parse(junit_path).findall(".//testcase")
    if not cases:
        raise ValueError("JUnit report contains no executed test cases")
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
        raise ValueError(f"JUnit suite did not pass: failures={failures}, errors={errors}")

    artifacts = {Path(item["filename"]).name: item for item in metadata.get("artifacts", [])}
    bundle = next((name for name in artifacts if name.lower().endswith(".zip")), None)
    installer = next((name for name in artifacts if name.lower().endswith("-setup.exe")), None)
    if not bundle or not installer or metadata.get("build_tools", {}).get("inno_setup") in (None, "", "NOT_BUILT"):
        raise ValueError("release metadata must evidence both portable ZIP and compiled installer")

    return {
        "schema": "drillmaster-windows-acceptance/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "git_sha": source_sha,
            "version": metadata["version"],
            "platform": metadata["platform"],
            "runner_platform": platform.platform(),
        },
        "repository_automation": {
            "windows_regression_suite": {
                "status": "PASS_WITH_SKIPS" if skipped else "PASS",
                "collected": len(cases),
                "passed": passed,
                "skipped": skipped,
                "failed": failures,
                "errors": errors,
                "skipped_tests": skipped_tests,
            },
            "portable_bundle_build": {"status": "PASS", "artifact": bundle,
                                       "sha256": artifacts[bundle]["sha256"]},
            "frozen_executable_smoke": {"status": "PASS", "mode": "isolated --package-smoke"},
            "installer_compilation": {"status": "PASS", "artifact": installer,
                                      "sha256": artifacts[installer]["sha256"],
                                      "inno_setup_version": metadata["build_tools"]["inno_setup"]},
            "source_release_gate": "SEPARATE_EXACT_SHA_WORKFLOW_REQUIRED",
        },
        "external_acceptance": {
            "interactive_clean_machine_install": "NOT_RUN",
            "interactive_upgrade_and_uninstall_data_retention": "NOT_RUN",
            "real_ddr_excel_operator_acceptance": "NOT_RUN",
            "real_ddr_pdf_acceptance": "NOT_RUN",
            "real_mineru_acceptance": "NOT_RUN",
            "production_database_acceptance": "NOT_RUN",
            "field_validation": "NOT_RUN",
            "operator_business_signoff": "NOT_RUN",
            "synthetic_workbook_scenario": "AUTOMATED_TEST_ONLY_NOT_REAL_DDR_ACCEPTANCE",
        },
        "decision": "WINDOWS_AUTOMATION_PASS; SOURCE_GATE_AND_EXTERNAL_ACCEPTANCE_REMAIN_SEPARATE",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument("--junit", required=True, type=Path)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    report = build_report(metadata_path=args.metadata, junit_path=args.junit, source_sha=args.source_sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Windows acceptance report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
