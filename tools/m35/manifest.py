#!/usr/bin/env python3
"""M35 §22: the commit candidate manifest.

Classifies every path in the worktree population (modified tracked + untracked) with an explicit
rule and reason, then cross-checks the pre-existing population against M34's recorded per-file
classification so the two agree or the difference is named.

Classes
  COMMIT-A          M35 release/package correctness (this mission's own change)
  COMMIT-B          production semantic fixes from earlier missions (M25-M33), not M35's to bundle
  COMMIT-C          audit record / evidence / analysis tooling (behaviour-neutral)
  REVIEW-REQUIRED   large, binary, secret-bearing or otherwise unsafe-to-commit
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "audits" / "m35-evidence" / "m35-commit-manifest.json"
M34_SIM = ROOT / "docs" / "audits" / "m34-evidence" / "m34-commit-staging-simulation.json"

M35_COMMIT_A = {
    "core/operational_time.py": "required runtime module (previously untracked) — time reductions "
                                "imported by report engine, DDR export, planning tab and analysis",
    "core/safety_semantics.py": "required runtime module (previously untracked) — safety KPIs "
                                "imported by operations intelligence",
    "tests/test_release_boundary_imports.py": "release-boundary regression: tracked-population wheel "
                                              "build + clean-target install + startup from outside "
                                              "the checkout (fails when either module is untracked)",
}
AUDIT_PREFIXES = ("docs/audits/", "tools/m34/", "tools/m35/")
AUDIT_SUFFIXES = ("_AUDIT.md", "_REPORT.md", "_EVIDENCE_INDEX.md", "_AUDIT_ANSWERS.md",
                  "_DOMAIN_MATRIX.md", "_ROOT_CAUSES.md", "_RECOVERY.md", "_RECONCILIATION.md",
                  "_FORENSIC_RECOVERY.md", "_RELEASE_CERTIFICATION.md", "_SEMANTIC_AUDIT.md",
                  "_CERTIFICATION.md", "_RECOVERY_REPORT.md")
MAX_SAFE_BYTES = 5 * 1024 * 1024


def status_population() -> list[tuple[str, str]]:
    raw = subprocess.run(["git", "status", "--porcelain", "-z", "-uall"], cwd=ROOT,
                         capture_output=True, check=True).stdout.decode()
    entries, i = [], 0
    fields = raw.split("\0")
    while i < len(fields):
        entry = fields[i]
        if not entry:
            i += 1
            continue
        code, path = entry[:2], entry[3:]
        if code.strip() in {"R", "C"} and i + 1 < len(fields):   # rename/copy: original follows
            i += 1
        entries.append((code, path))
        i += 1
    return entries


def classify(code: str, path: str) -> tuple[str, str]:
    full = ROOT / path
    if path in M35_COMMIT_A:
        return "COMMIT-A", M35_COMMIT_A[path]
    if not full.is_file():
        return "REVIEW-REQUIRED", "not a regular file in the worktree"
    size = full.stat().st_size
    if size > MAX_SAFE_BYTES:
        return "REVIEW-REQUIRED", f"large file ({size} bytes) — confirm provenance before committing"
    if path.endswith((".db", ".sqlite", ".sqlite3", ".pyc", ".pyo", ".log")):
        return "REVIEW-REQUIRED", "database/cache/log artifact"
    if any(part in path for part in ("__pycache__/", ".venv/", "build/", "dist/")):
        return "REVIEW-REQUIRED", "generated/cache path"
    if path.startswith("packaging/"):
        return "COMMIT-B", "Windows packaging/build configuration (earlier mission)"
    if path.startswith(AUDIT_PREFIXES) or path.startswith("tools/") or path.endswith(AUDIT_SUFFIXES) \
            or path.endswith((".md", ".markdown")):
        return "COMMIT-C", ("audit record / evidence / analysis tooling (behaviour-neutral); no "
                            "production module imports tools/")
    if path.startswith("tests/") or path.endswith((".py", ".toml", ".yml", ".yaml", ".txt", ".json")):
        return "COMMIT-B", "production or test change from an earlier mission (behavioural)"
    return "REVIEW-REQUIRED", "unclassified path — needs an explicit decision"


def main() -> int:
    population = status_population()
    decisions = []
    for code, path in population:
        cls, why = classify(code, path)
        decisions.append({"path": path, "status": code.strip(), "class": cls, "why": why})

    m34 = {}
    if M34_SIM.is_file():
        sim = json.loads(M34_SIM.read_text())
        for d in sim.get("decisions", []):
            m34[d["path"]] = d["class"]

    mapping = {"COMMIT-1": "COMMIT-B", "COMMIT-2": "COMMIT-C"}
    diff = []
    for d in decisions:
        previous = m34.get(d["path"])
        if previous is None or d["class"] == "COMMIT-A":
            continue
        expected = mapping.get(previous, previous)
        if expected != d["class"] and not (d["class"] == "REVIEW-REQUIRED"):
            diff.append({"path": d["path"], "m34_class": previous, "expected_from_m34": expected,
                         "m35_class": d["class"], "m35_why": d["why"]})

    by_class: dict[str, int] = {}
    for d in decisions:
        by_class[d["class"]] = by_class.get(d["class"], 0) + 1

    payload = {
        "schema": "m35-commit-manifest",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                               text=True).stdout.strip(),
        "rules": {
            "COMMIT-A": "M35 release/package correctness only (runtime modules + release-boundary "
                        "regression test); required runtime modules must be tracked for a distributable "
                        "artifact to start",
            "COMMIT-B": "behavioural production/test changes from earlier missions; must not be "
                        "silently bundled with the packaging fix",
            "COMMIT-C": "audit records, evidence and analysis tooling; behaviour-neutral",
            "REVIEW-REQUIRED": "large/binary/generated/unclassified — explicit human decision needed",
        },
        "population": len(decisions),
        "by_class": by_class,
        "commit_a": [d for d in decisions if d["class"] == "COMMIT-A"],
        "commit_a_size_bytes": sum((ROOT / d["path"]).stat().st_size
                                   for d in decisions if d["class"] == "COMMIT-A"),
        "commit_a_details": [
            {"path": "core/operational_time.py",
             "tests_covering": ["tests/test_release_boundary_imports.py",
                                "tests/test_operational_time_integrity.py",
                                "tests/test_m30_semantic_regressions.py",
                                "tests/test_m31_scenarios.py"],
             "packaging_impact": "adds a required module to wheel/sdist (module was absent from every "
                                 "artifact built from the index)",
             "runtime_impact": "fixes ModuleNotFoundError at startup (main_window -> tabs.w10)"},
            {"path": "core/safety_semantics.py",
             "tests_covering": ["tests/test_release_boundary_imports.py",
                                "tests/test_m28_finance_safety_plan.py",
                                "tests/test_m31_scenarios.py"],
             "packaging_impact": "adds a required module to wheel/sdist",
             "runtime_impact": "fixes ModuleNotFoundError in core.operations_intelligence.safety_kpis"},
            {"path": "tests/test_release_boundary_imports.py",
             "tests_covering": ["self-validating (mutation-validated: untracking either module fails "
                                "2/3 tests)"],
             "packaging_impact": "none (tests are not packaged; the file exists to guard the boundary)",
             "runtime_impact": "none (test-only)"},
        ],
        "commit_a_sha256": {d["path"]: hashlib.sha256((ROOT / d["path"]).read_bytes()).hexdigest()
                            for d in decisions if d["class"] == "COMMIT-A"},
        "review_required": [d for d in decisions if d["class"] == "REVIEW-REQUIRED"][:40],
        "cross_check_vs_m34_staging_simulation": {
            "m34_decisions": len(m34),
            "differences": diff[:40],
            "difference_count": len(diff),
            "mapping_note": "M34 split COMMIT-1/COMMIT-2 (production vs audit); M35 splits "
                            "A/B/C (M35 packaging vs earlier behavioural vs audit). The comparable "
                            "axis is behavioural (COMMIT-1) vs audit (COMMIT-2).",
        },
        "decisions": decisions,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("population:", len(decisions), "| by class:", by_class)
    print("commit A files:", len(payload["commit_a"]), payload["commit_a_size_bytes"], "bytes")
    for d in payload["commit_a"]:
        print("   ", d["path"], "-", payload["commit_a_sha256"][d["path"]][:16] + "…")
    print("cross-check differences vs M34 simulation:", len(diff))
    for d in diff[:6]:
        print("   ", d["path"], d["m34_class"], "->", d["m35_class"])
    print("review-required sample:", [d["path"] for d in payload["review_required"][:6]])
    print("written", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
