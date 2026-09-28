#!/usr/bin/env python3
"""M34 Part O: mutation control harness.

Every fix must be *falsifiable by construction*: reintroduce the defect it removed and the
fix's own regression test must fail.  The harness

1. reads the file, applies exactly one regex substitution (must match exactly once — a
   mutant whose anchor is gone is recorded SKIPPED, never counted as killed),
2. runs the selector the fix claims,
3. restores the original bytes and re-hashes,
4. classifies KILLED / SURVIVED / SKIPPED / RESTORE-FAILURE, against the mutation's declared
   expectation (a deliberately equivalent mutant is expected to SURVIVE and is labelled so).

The harness refuses to leave a mutant behind: a restore mismatch aborts the run.
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
OUT = ROOT / "docs" / "audits" / "m34-evidence" / "m34-mutation-controls.json"
PY = "/home/user/verify-venv/bin/python"

ENV = dict(os.environ)
ENV.update({
    "PYTHONDONTWRITEBYTECODE": "1",
    "LD_LIBRARY_PATH": "/tmp/qtstub",
    "QT_QPA_PLATFORM": "offscreen",
    "DRILLMASTER_AI_IMPORT": "0",
})

# ---------------------------------------------------------------- mutants
# expectation: "killed" = the defect's return must break its own test;
#               "equivalent-survivor" = the mutation cannot change behaviour and must survive.
MUTANTS = [
    dict(id="M34-M-DIALOG", fixes=["M32-FIX-001"], path="dialogs/drilling_report_dialogs.py",
         pattern=r"spin\.setMinimum\(-1\)", repl="spin.setMinimum(0)",
         selector=["tests/test_m31_scenarios.py::test_bit_record_dialog_keeps_unrecorded_measurements_blank"],
         expectation="killed", defect="a real 0 and an unrecorded measurement become indistinguishable"),
    dict(id="M34-M-EXPORT", fixes=["M32-FIX-002"], path="core/professional_export.py",
         pattern=r"value=log\.duration", repl="value=log.duration or 0",
         selector=["tests/test_m31_scenarios.py::test_professional_export_leaves_unrecorded_duration_blank"],
         expectation="killed", defect="unrecorded duration exports as a measured 0 h"),
    dict(id="M34-M-HIERARCHY", fixes=["M32-FIX-003"], path="core/database.py",
         pattern=r"key=lambda s: \(s\.depth_from is None, s\.depth_from or 0\)",
         repl="key=lambda s: (False, s.depth_from or 0)",
         selector=["tests/test_m31_scenarios.py::test_full_hierarchy_orders_unknown_section_depth_last"],
         expectation="killed", defect="an unknown depth sorts as 0 (first) again"),
    dict(id="M34-M-NPT", fixes=["M32-FIX-004"], path="core/database.py",
         pattern=r"(\s+)if log\.duration is None:(\s*\n\s+# NPTReport\.duration_hours is NOT NULL)",
         repl=lambda m: f"{m.group(1)}if False:{m.group(2)}",
         selector=["tests/test_m31_scenarios.py::test_derived_npt_skips_logs_without_a_recorded_duration"],
         expectation="killed", defect="derived NPT is written from a missing duration again"),
    dict(id="M34-M-CODEHOURS", fixes=["M32-FIX-005"], path="core/database.py",
         pattern=r"if log\.duration is None:\s*\n(\s+)code_usage\[code\]\[\"unrecorded_hours\"\] \+= 1",
         repl=lambda m: f"if False:\n{m.group(1)}code_usage[code][\"unrecorded_hours\"] += 1",
         selector=["tests/test_m31_scenarios.py::test_activity_code_usage_hours_are_unknown_when_a_duration_is_missing"],
         expectation="killed", defect="an unrecorded duration is folded into the usage hours"),
    dict(id="M34-M-VALIDATOR", fixes=["M32-FIX-006"], path="core/validators.py",
         pattern=r"unrecorded = sum\(1 for value in recorded if value is None\)", repl="unrecorded = 0",
         selector=["tests/test_m31_scenarios.py::test_legacy_time_log_validator_reports_unrecorded_duration"],
         expectation="killed", defect="the legacy validator reports a complete 24 h again"),
    dict(id="M34-M-ROP", fixes=["M32-FIX-007"], path="core/managers.py",
         pattern=r"return r\.values\.get\(\"rop\"\)", repl='return r.values.get("rop", 0)',
         selector=["tests/test_m31_scenarios.py::test_engine_result_without_a_rop_value_is_unknown"],
         expectation="killed", defect="a failed/absent ROP is reported as 0 m/hr"),
    dict(id="M34-M-TABPERSIST", fixes=["M32-FIX-008"], path="tabs/w3_drilling_report.py",
         pattern=r"return None if spin\.value\(\) <= spin\.minimum\(\) else spin\.value\(\)",
         repl="return spin.value()",
         selector=["tests/test_m31_scenarios.py::test_drilling_tab_persists_unknown_for_uncomputed_values"],
         expectation="killed", defect="the 'not computed' sentinel is persisted as a number"),
    dict(id="M34-M-CASING-FABRICATE", fixes=["M33-FIX-CASING"],
         path="core/engineering/engines/casing.py",
         pattern=r"\"fyax_psi\": round\(yp_ax, 1\) if fax_supplied else None,",
         repl='"fyax_psi": round(yp_ax, 1),',
         selector=["tests/test_casing_absent_load_semantics.py"],
         expectation="killed", defect="an absent axial load is reported as a measured stress"),
    dict(id="M34-M-CASING-ZERONONE", fixes=["M33-FIX-CASING"],
         path="core/engineering/engines/casing.py",
         pattern=r"fax_supplied = not \(axial_tension_lbf is None or axial_tension_lbf == \"\"\)",
         repl='fax_supplied = not (axial_tension_lbf is None or axial_tension_lbf == "" or axial_tension_lbf == 0)',
         selector=["tests/test_casing_absent_load_semantics.py"],
         expectation="killed", defect="a load supplied as exactly zero is misread as absent"),
    dict(id="M34-M-NONETOZERO", fixes=["M33-FIX-DATAQUALITY"], path="core/data_quality.py",
         pattern=r"unrecorded = sum\(1 for log in logs if log\.duration is None\)", repl="unrecorded = 0",
         selector=["tests/test_m31_scenarios.py::test_time_coverage_is_unknown_when_a_duration_is_missing"],
         expectation="killed", defect="24 h coverage is computed over a missing duration again"),
    dict(id="M34-M-DURATIONORZERO", fixes=["M32-FIX-005"], path="core/database.py",
         pattern=r"else:\s*\n(\s+)code_usage\[code\]\[\"hours\"\] \+= log\.duration",
         repl=lambda m: f"else:\n{m.group(1)}code_usage[code][\"hours\"] += log.duration or 0",
         selector=["tests/test_m31_scenarios.py::test_activity_code_usage_hours_are_unknown_when_a_duration_is_missing"],
         expectation="equivalent-survivor",
         defect="inside the recorded-duration branch 'or 0' can only differ for 0.0, where x or 0 == 0"),
    dict(id="M34-M-CLAMPRESTORE", fixes=["M33-FIX-QTCLAMP"], path="tabs/w3_drilling_report.py",
         pattern=r"if value > spin\.maximum\(\):\s*\n\s+spin\.setMaximum\(value\)\s*\n",
         repl="",
         selector=["tests/test_m31_scenarios.py::test_derived_avg_rop_display_is_not_silently_clamped"],
         expectation="killed", defect="a computed value above the current maximum is silently truncated"),
    dict(id="M34-M-QT99CLAMP", fixes=["M33-FIX-QTCLAMP"], path="tabs/w3_drilling_report.py",
         pattern=r"if maximum is not None:\s*\n\s+spin\.setMaximum\(maximum\)\s*\n",
         repl="",
         selector=["tests/test_m31_scenarios.py::test_derived_avg_rop_display_is_not_silently_clamped"],
         expectation="killed", defect="the widget falls back to Qt's default 99.99 maximum"),
    dict(id="M34-M-OWNERSHIP", fixes=["M26/M32 ownership contract"], path="core/database.py",
         pattern=r"if report is not None and report\.well_id != well_id:\s*\n\s+raise OwnershipIntegrityError\(",
         repl="if False and report is not None and report.well_id != well_id:\n        raise OwnershipIntegrityError(",
         selector=["tests/test_report_scoped_ownership_m26.py"],
         expectation="killed", defect="a report-scoped snapshot may claim a foreign well again"),
    dict(id="M34-M-QTSINGLETON", fixes=["M32-FIX-009"], path="tests/test_autosave_manager_regression.py",
         pattern=r"    existing = QCoreApplication\.instance\(\)\s*\n    if existing is not None:\s*\n        return existing\s*\n",
         repl="",
         selector=["tests/test_m31_scenarios.py", "tests/test_autosave_manager_regression.py"],
         expectation="killed",
         defect="a new, non-widget-capable fallback application is built per test file; the defect "
                "only manifests when another file already created the process-wide application, so "
                "the oracle runs both files in one process"),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(selector: list[str], timeout: int = 900) -> dict:
    cmd = [PY, "-m", "pytest", *selector, "-p", "no:cacheprovider", "-q", "-W", "ignore::DeprecationWarning"]
    try:
        proc = subprocess.run(cmd, cwd=ROOT, env=ENV, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"exit_code": None, "outcome": "TIMEOUT", "last_line": ""}
    tail = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
    return {"exit_code": proc.returncode,
            "outcome": "PASS" if proc.returncode == 0 else ("USAGE-ERROR" if proc.returncode == 4 else "FAIL"),
            "last_line": (tail[-1] if tail else "")[:200]}


def main() -> int:
    only = None
    for arg in sys.argv[1:]:
        if arg.startswith("--only="):
            only = set(arg.split("=", 1)[1].split(","))
    results, files_touched = [], {}
    aborted = False
    prior = {}
    if only and OUT.exists():
        for r in json.loads(OUT.read_text()).get("results", []):
            prior[r["id"]] = r
    for m in MUTANTS:
        if only and m["id"] not in only:
            if m["id"] in prior:
                results.append(prior[m["id"]])
                files_touched.setdefault(m["path"], {"before": prior[m["id"]].get("sha256_before", ""),
                                                     "after": prior[m["id"]].get("sha256_after", ""),
                                                     "restored_byte_identical": prior[m["id"]].get("restored_byte_identical", True)})
            continue
        path = ROOT / m["path"]
        before = sha256(path)
        files_touched.setdefault(m["path"], {"before": before})
        text = path.read_text(encoding="utf-8")
        repl = m["repl"]
        try:
            new_text, n = re.subn(m["pattern"], repl, text, count=1, flags=re.S)
        except re.error as exc:
            results.append({**{k: m[k] for k in ("id", "path", "expectation", "defect")},
                            "outcome": "SKIPPED-PATTERN-ERROR", "detail": str(exc)})
            continue
        if n != 1:
            results.append({**{k: m[k] for k in ("id", "path", "expectation", "defect")},
                            "outcome": "SKIPPED-ANCHOR-NOT-FOUND",
                            "detail": f"pattern matched {n} times, expected exactly 1"})
            print(f"{m['id']:24} SKIPPED-ANCHOR-NOT-FOUND", flush=True)
            continue

        path.write_text(new_text, encoding="utf-8")
        try:
            run_info = run(m["selector"])
        finally:
            path.write_text(text, encoding="utf-8")
        after = sha256(path)
        restored = after == before
        if not restored:
            aborted = True

        if not restored:
            outcome = "RESTORE-FAILURE"
        elif run_info["outcome"] == "USAGE-ERROR":
            outcome = "INVALID-SELECTOR"
        elif m["expectation"] == "killed":
            outcome = "KILLED" if run_info["outcome"] == "FAIL" else "SURVIVED"
        else:
            outcome = "SURVIVED-AS-EXPECTED" if run_info["outcome"] == "PASS" else "UNEXPECTEDLY-KILLED"

        results.append({**{k: m[k] for k in ("id", "path", "expectation", "defect")},
                        "fixes": m["fixes"], "selector": m["selector"],
                        "outcome": outcome, "pytest": run_info,
                        "restored_byte_identical": restored,
                        "sha256_before": before, "sha256_after": after})
        print(f"{m['id']:24} {outcome:20} {run_info['outcome']:6} {run_info['last_line'][:60]}", flush=True)
        if aborted:
            break

    for p, rec in files_touched.items():
        rec["after"] = sha256(ROOT / p)
        rec["restored_byte_identical"] = rec["before"] == rec["after"]

    counts = {}
    for r in results:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    payload = {
        "schema": "m34-mutation-controls",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": "one regex substitution per mutant (exactly-once match required), the fix's own "
                  "regression test as the oracle, byte-identical restore verified by sha256",
        "total": len(results), "counts": counts,
        "killed": counts.get("KILLED", 0),
        "survivors": [r["id"] for r in results if r["outcome"] in ("SURVIVED", "UNEXPECTEDLY-KILLED")],
        "skipped": [r["id"] for r in results if r["outcome"].startswith("SKIPPED")],
        "restore_failures": [p for p, rec in files_touched.items() if not rec["restored_byte_identical"]],
        "harness_self_check": {"files": files_touched,
                               "all_restored": all(r["restored_byte_identical"] for r in files_touched.values())},
        "results": results,
        "rule_zero_note": "no mutant remains in the worktree; the abort-on-mismatch path exists so a "
                          "failed restore cannot be silently ignored",
    }
    OUT.write_text(json.dumps(payload, indent=1))
    print(f"\nwritten {OUT.relative_to(ROOT)}  {counts}")
    return 0 if (not payload["survivors"] and not payload["restore_failures"] and not aborted) else 1


if __name__ == "__main__":
    raise SystemExit(main())
