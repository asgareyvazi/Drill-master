#!/usr/bin/env python3
"""M34 Part B/C: independently re-verify every M32 and M33 fix from the current source.

Nothing here trusts an earlier report.  For each fix the verifier records:

* the sha256 of every file the fix touched, *now*;
* whether the fix's stated contract is still present in the source, checked by regex
  probes derived from the fix's own "after" description (a moved line still passes,
  a reverted line fails);
* the sha256 the fix's own record claimed at the time (M32 post_fix_hashes /
  M33 fix records) so a later change by another mission is visible as a mismatch
  rather than silently accepted;
* the outcome of a targeted run of the fix's own regression test.

Verdict per fix: VERIFIED / PARTIAL / INVALIDATED / MISSING, each with the failing
probe named.  Written to docs/audits/m34-evidence/m34-fix-reverification.json.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "audits" / "m34-evidence" / "m34-fix-reverification.json"
PY = "/home/user/verify-venv/bin/python"

ENV = dict(os.environ)
ENV.update({
    "PYTHONDONTWRITEBYTECODE": "1",
    "LD_LIBRARY_PATH": "/tmp/qtstub",
    "QT_QPA_PLATFORM": "offscreen",
    "DRILLMASTER_AI_IMPORT": "0",
})

# ---------------------------------------------------------------- fix definitions
# ``checks`` are (regex, human description) pairs read from the fix's own "after" text.
FIXES = [
    {
        "fix_id": "M32-FIX-001", "mission": "M32", "kind": "fabricated-measurement",
        "path": "dialogs/drilling_report_dialogs.py",
        "claim": "unrecorded measurements stay blank: sentinel minimum, 'Not recorded' text, "
                 "empty-string persistence, em dash for an uncomputed rate",
        "checks": [
            (r"spin\.setMinimum\(-1\)", "sentinel minimum keeps a real 0 distinguishable"),
            (r"setSpecialValueText\(\"Not recorded\"\)", "the blank state is labelled"),
            (r"def _spin_text\(", "persistence helper exists"),
            (r"def _loaded\(", "absent values survive a reload"),
        ],
        "tests": ["tests/test_m31_scenarios.py::test_bit_record_dialog_keeps_unrecorded_measurements_blank",
                  "tests/test_m31_scenarios.py::test_bha_component_dialog_keeps_unrecorded_dimensions_blank"],
        "recorded_hash": "4c296617482bc11721365e6b0a4389a293d1904272f0b849c55943f0b4a373c0",
    },
    {
        "fix_id": "M32-FIX-002", "mission": "M32", "kind": "fabricated-measurement",
        "path": "core/professional_export.py",
        "claim": "an unrecorded duration exports as an empty cell, never 0 hours",
        "checks": [
            (r"value=log\.duration\b", "the raw value (None included) is written"),
            (r"Unrecorded duration exports as an empty cell", "the intent is documented"),
        ],
        "tests": ["tests/test_m31_scenarios.py::test_professional_export_leaves_unrecorded_duration_blank",
                  "tests/test_m31_scenarios.py::test_ddr_excel_leaves_unrecorded_measurements_empty"],
        "recorded_hash": "96878cf690f49d01c29a0b38323a761e275c9cddec9ff2d98d387a060dd73727",
    },
    {
        "fix_id": "M32-FIX-003", "mission": "M32", "kind": "ordering-unknown-last",
        "path": "core/database.py",
        "claim": "an unknown section depth sorts last instead of as 0",
        "checks": [
            (r"s\.depth_from is None,\s*s\.depth_from or 0",
             "the sort key puts the unknown-depth flag before the value"),
        ],
        "tests": ["tests/test_m31_scenarios.py::test_full_hierarchy_orders_unknown_section_depth_last"],
        "recorded_hash": "578d6a9c3eb83c405d7c3fb5d532416c2612137117a7bfa6d8d32b83562e54c2",
    },
    {
        "fix_id": "M32-FIX-004", "mission": "M32", "kind": "failure-as-zero",
        "path": "core/database.py",
        "claim": "derived NPT skips logs without a recorded duration and warns",
        "checks": [
            (r"unrecorded_npt", "the unrecorded count is tracked"),
            (r"Derived NPT skipped for .*log\(s\) with no recorded duration", "the skip is reported"),
        ],
        "tests": ["tests/test_m31_scenarios.py::test_derived_npt_skips_logs_without_a_recorded_duration"],
    },
    {
        "fix_id": "M32-FIX-005", "mission": "M32", "kind": "failure-as-zero",
        "path": "core/database.py",
        "claim": "activity-code usage hours are unknown when a duration is missing",
        "checks": [
            (r"\"unrecorded_hours\"", "unrecorded hours are carried separately"),
            (r"code_usage\[code\]\[\"unrecorded_hours\"\] \+= 1", "the missing duration is counted"),
        ],
        "tests": ["tests/test_m31_scenarios.py::test_activity_code_usage_hours_are_unknown_when_a_duration_is_missing"],
        "recorded_hash": "578d6a9c3eb83c405d7c3fb5d532416c2612137117a7bfa6d8d32b83562e54c2",
    },
    {
        "fix_id": "M32-FIX-006", "mission": "M32", "kind": "failure-as-zero",
        "path": "core/validators.py",
        "claim": "the legacy time-log validator reports an unrecorded duration instead of 0 h",
        "checks": [
            (r"unrecorded = sum\(1 for value in recorded if value is None\)",
             "unrecorded entries are counted, not read as zero"),
            (r"have no recorded duration; total hours incomplete", "the report states it"),
        ],
        "tests": ["tests/test_m31_scenarios.py::test_legacy_time_log_validator_reports_unrecorded_duration"],
        "recorded_hash": "ae1f69d157a55d3691df42b71379973150b4d57cd56e1ea8178b5cb60152ad0c",
    },
    {
        "fix_id": "M32-FIX-007", "mission": "M32", "kind": "failure-as-zero",
        "path": "core/managers.py",
        "claim": "a failed engine calculation is not reported as 0 ROP/TFA/HSI",
        "checks": [
            (r"if not r\.success:\s*\n\s*return None", "failure returns None, not a number"),
            (r"return r\.values\.get\(\"rop\"\)", "a missing ROP stays missing"),
        ],
        "tests": ["tests/test_m31_scenarios.py::test_engine_result_without_a_rop_value_is_unknown"],
        "recorded_hash": "1c0f33c4ca47170a995b35d8b33126fb48b473f0c0dfb4dd1597ce8c36d2609b",
    },
    {
        "fix_id": "M32-FIX-008", "mission": "M32", "kind": "failure-as-zero",
        "path": "tabs/w3_drilling_report.py",
        "claim": "the drilling tab persists 'unknown' for uncomputed derived values",
        "checks": [
            (r"def _calc_value\(", "the reader helper exists"),
            (r"return None if spin\.value\(\) <= spin\.minimum\(\) else spin\.value\(\)",
             "an untouched field reads as None"),
            (r"\"tfa\": _calc_value\(self\.tfa_value\)", "collect_data uses the unknown-aware reader"),
        ],
        "tests": ["tests/test_m31_scenarios.py::test_drilling_tab_persists_unknown_for_uncomputed_values"],
        "recorded_hash": "fd6eca6ceac069775a800a52b89cd267c91f729f1847d54d96c74c00ac4a40c0",
        "note": "M33 later changed this file (Qt clamp fix); a hash mismatch against the M32 "
                "record is expected and the contract probes above are the operative check",
    },
    {
        "fix_id": "M32-FIX-009", "mission": "M32", "kind": "test-infrastructure",
        "path": "tests/test_autosave_manager_regression.py",
        "claim": "the suite runs on a widget-capable QApplication instead of a bare QCoreApplication",
        "checks": [
            (r"def _widget_capable_application\(", "the helper exists"),
            (r"QApplication\(\[\]\)", "a widget-capable application is built"),
            (r"QCoreApplication\.instance\(\)", "an existing application is reused"),
        ],
        "tests": ["tests/test_autosave_manager_regression.py"],
        "recorded_hash": "f07170668dbaf302ea6b3f0d633dd9686bfc6e1547f4d05253d03819cc642860",
    },
    {
        "fix_id": "M32-FIX-010", "mission": "M32", "kind": "test-infrastructure",
        "path": "tests/test_m31_scenarios.py",
        "claim": "widget scenarios fail loudly on a bare QCoreApplication instead of aborting the session",
        "checks": [
            (r"def _qt_app\(", "the helper exists"),
            (r"widget tests need a QApplication", "a bare application is rejected loudly"),
        ],
        "tests": ["tests/test_m31_scenarios.py::test_drilling_tab_persists_unknown_for_uncomputed_values"],
        "recorded_hash": "8e5b977431518f52d2d0256a11c070cb9abaa7a191ce67c4f8699402d22a60b8",
    },
    {
        "fix_id": "M33-FIX-CASING", "mission": "M33", "kind": "missing-vs-zero",
        "path": "core/engineering/engines/casing.py",
        "claim": "an absent biaxial/internal-pressure load is reported as not recorded, while an "
                 "explicit zero load stays a measured zero, with explicit warnings",
        "checks": [
            (r"fax_supplied = not \(axial_tension_lbf is None or axial_tension_lbf == \"\"\)",
             "suppliedness is tracked separately from the value"),
            (r"\"fyax_psi\": round\(yp_ax, 1\) if fax_supplied else None",
             "an absent load yields None, not a fabricated stress"),
            (r"Axial tension not supplied", "the absence is warned about"),
            (r"axial_tension_supplied", "suppliedness is part of the reported values"),
        ],
        "tests": ["tests/test_casing_absent_load_semantics.py"],
        "recorded_hash": "17eb484b1a095712",
        "hash_prefix": True,
    },
    {
        "fix_id": "M33-FIX-DATAQUALITY", "mission": "M33", "kind": "failure-as-zero",
        "path": "core/data_quality.py",
        "claim": "24h time coverage reports 'unknown' when an entry has no recorded duration",
        "checks": [
            (r"unrecorded = sum\(1 for log in logs if log\.duration is None\)",
             "unrecorded entries are counted before the sum"),
            (r"coverage cannot be computed", "the metric explains why it is unknown"),
            (r"value=None", "the metric value is None, not 0"),
        ],
        "tests": ["tests/test_m31_scenarios.py::test_time_coverage_is_unknown_when_a_duration_is_missing",
                  "tests/test_m31_scenarios.py::test_time_coverage_is_computed_when_every_duration_is_recorded"],
        "recorded_hash": "0151a92768ec15d1",
        "hash_prefix": True,
    },
    {
        "fix_id": "M33-FIX-QTCLAMP", "mission": "M33", "kind": "ui-truncation",
        "path": "tabs/w3_drilling_report.py",
        "claim": "derived-value displays carry an explicit domain maximum and never silently clamp",
        "checks": [
            (r"def _calc_spin\(spin, maximum=None\)", "the domain bound is an explicit parameter"),
            (r"spin\.setMinimum\(-1\)", "the 'not computed' sentinel is the minimum"),
            (r"if value > spin\.maximum\(\):\s*\n\s*spin\.setMaximum\(value\)",
             "a real value above the current maximum raises it instead of being truncated"),
            (r"_calc_spin\(QDoubleSpinBox\(\), 500\)", "avg_rop carries the documented 0-500 m/hr bound"),
        ],
        "tests": ["tests/test_m31_scenarios.py::test_derived_avg_rop_display_is_not_silently_clamped"],
        "recorded_hash": "e2764c18e9756705",
        "hash_prefix": True,
    },
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_pytest(selectors: list[str], timeout: int = 900) -> dict:
    cmd = [PY, "-m", "pytest", *selectors, "-p", "no:cacheprovider", "-q", "-W", "ignore::DeprecationWarning"]
    try:
        proc = subprocess.run(cmd, cwd=ROOT, env=ENV, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"exit_code": None, "outcome": "TIMEOUT", "last_line": "", "selectors": selectors}
    tail = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
    last = tail[-1] if tail else ""
    outcome = "PASS" if proc.returncode == 0 else ("USAGE-ERROR" if proc.returncode == 4 else "FAIL")
    return {"exit_code": proc.returncode, "outcome": outcome, "last_line": last[:200],
            "selectors": selectors, "stdout_tail": "\n".join(tail[-6:])[:1500]}


def main() -> int:
    results = []
    for fix in FIXES:
        path = ROOT / fix["path"]
        text = path.read_text(encoding="utf-8", errors="replace")
        current = sha256(path)
        probe_results = []
        for pattern, description in fix["checks"]:
            found = re.search(pattern, text, re.S) is not None
            probe_results.append({"check": description, "present": found})
        missing = [p["check"] for p in probe_results if not p["present"]]

        recorded = fix.get("recorded_hash")
        if recorded:
            same = current.startswith(recorded) if fix.get("hash_prefix") else current == recorded
            hash_state = "SAME-AS-RECORDED" if same else "DIFFERS-FROM-RECORDED"
        else:
            hash_state = "NO-RECORDED-HASH"

        test_run = run_pytest(fix["tests"])
        if test_run["outcome"] != "PASS":
            verdict = "INVALIDATED" if missing else "PARTIAL"
        elif missing:
            verdict = "PARTIAL"
        else:
            verdict = "VERIFIED"
        results.append({
            "fix_id": fix["fix_id"], "mission": fix["mission"], "kind": fix["kind"],
            "path": fix["path"], "claim": fix["claim"],
            "current_sha256": current, "recorded_sha256": recorded, "hash_state": hash_state,
            "probes": probe_results, "missing_probes": missing,
            "test_run": test_run, "verdict": verdict, "note": fix.get("note"),
        })
        print(f"{fix['fix_id']:22} {verdict:11} {hash_state:20} {test_run['outcome']:6} "
              f"{test_run['last_line'][:70]}", flush=True)

    counts = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    payload = {
        "schema": "m34-fix-reverification",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": "source contract probes (regex derived from each fix's own after-state) + "
                  "targeted regression run in the pinned environment; every probe that fails is "
                  "named, no fix is accepted from an earlier report",
        "environment": {
            "python": sys.version.split()[0], "pytest_platform": "offscreen",
            "LD_LIBRARY_PATH": "/tmp/qtstub", "DRILLMASTER_AI_IMPORT": "0",
            "note": "Qt is the headless stub set; native-GUI acceptance is NOT claimed",
        },
        "head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                               text=True).stdout.strip(),
        "fixes": results, "counts": counts,
        "verified": counts.get("VERIFIED", 0), "total": len(results),
    }
    OUT.write_text(json.dumps(payload, indent=1))
    print(f"\nwritten {OUT.relative_to(ROOT)}  {counts}")
    return 0 if counts.get("VERIFIED", 0) == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
