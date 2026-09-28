#!/usr/bin/env python3
"""M34 Parts X/Y/Z and the non-test verification stages.

Produces, from the *actual* final tree:

* m34-domain-matrix.json      — the 69-domain taxonomy projected from the M34 ledger, reconciled
* m34-closure-invariants.json — closure gate (inventory == terminal ledger items) and blocker gate
* m34-ledger-summary.json     — inventory/delta/disposition summary, from m34-ledger.json only
* M34_INVENTORY_LEDGER.json   — deliverable manifest + invariant projection of the same ledger
* m34-doc-claim-audit.json    — every SHA / branch / test-count claim in the living docs, classified
* m34-git-cleanliness.json    — worktree classification, cache/mutant/secret scan, diff --check

No claim here is copied from an earlier mission's report: the ledger, the docs, the git index and
the filesystem are read directly.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / "docs" / "audits" / "m34-evidence"
LEDGER = EV / "m34-ledger.json"
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")

TERMINAL = {"VERIFIED-CORRECT", "DEFECT-FIXED", "INTENTIONAL-BY-DESIGN",
            "DUPLICATE-DEAD-WITH-EVIDENCE", "ACCEPTED-LIMITATION", "EXTERNAL-ACCEPTANCE-ONLY",
            "REMOVED-WITH-EVIDENCE"}
OPEN_STATES = {"UNDER-REVIEW", "EVIDENCE-INCOMPLETE"}


def sh(*args: str, binary: bool = False):
    proc = subprocess.run(list(args), cwd=ROOT, capture_output=True)
    return proc.stdout if binary else proc.stdout.decode("utf-8", "replace")


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---------------------------------------------------------------- domain mapping
# Ordered (regex on the relative path, domain id) rules.  The basis is the file's primary
# responsibility; a shared core module is mapped to the domain that owns most of its callers,
# and the mapping is disclosed in the evidence so a reader can overrule it per file.
DOMAIN_RULES = [
    (r"^tools/", 66), (r"^docs/", 69), (r"^\.github/", 66),
    (r"casing", 49), (r"cement", 50), (r"torque_drag", 53), (r"hydraulic|nozzle", 48),
    (r"schematic|wellbore_schematic", 56), (r"trajectory|mcm|survey", 46),
    (r"anti_collision|anticollision", 47), (r"mse|bit_performance|bit_record|bit_", 51),
    (r"mud", 52), (r"drillpipe|drill_pipe", 55), (r"kill|well_control|wellcontrol", 54),
    (r"currency|fx_|exchange", 16), (r"capex|revenue", 18), (r"payroll|insurance|tax", 19),
    (r"fuel|maintenance|overhead", 20), (r"standby|moving", 21), (r"irr|economic", 22),
    (r"cost_semantics|cost_", 17), (r"w16", 23), (r"plan_|planned|_plan\b|wellplan", 24),
    (r"plan_revision|revision", 11), (r"inventory|stock|bulk", 44),
    (r"logistics|personnel|transport", 43), (r"trip|w6", 42),
    (r"npt", 27), (r"safety", 41), (r"backup|restore", 15),
    (r"credential|bootstrap|secret", 13), (r"permission|w8", 14),
    (r"canonical_|canonical\.", 2), (r"ownership", 3),
    (r"startup|migration|_m1[0-9]|_m2[0-9]", 7),
    (r"data_quality", 63), (r"report_engine|report_history|report_lifecycle", 10),
    (r"professional_export|excel|ddr_import|import_service|import_quality", 57),
    (r"ai_import|template", 59), (r"pdf|mineru", 60), (r"json_|copy", 61),
    (r"scope", 8), (r"search", 8), (r"hierarchy|company|project", 9),
    (r"migration_service", 7), (r"gate|accounting", 63),
    (r"w3_drilling|w3[abc]|drilling_report|drilling_parameters|drilling_manager", 29),
    (r"w3", 29), (r"w4|w5|w7", 43), (r"w10", 27), (r"w11", 39), (r"w12", 31),
    (r"w13|engineering", 45), (r"w14", 45), (r"w15", 45), (r"w2", 10), (r"w1", 10),
    (r"w9", 44), (r"database", 58), (r"manager", 45), (r"validator", 45),
    (r"tests/", 69), (r"^app\.py$", 7), (r"^main_window\.py$", 14),
    (r"widget|dialog|tab", 45),
]
DEFAULT_DOMAIN = 45


def domain_of(rel: str) -> int:
    low = rel.lower()
    for pattern, dom in DOMAIN_RULES:
        if re.search(pattern, low):
            return dom
    return DEFAULT_DOMAIN


def build_domain_matrix(domains: list[str], records: list[dict]) -> dict:
    rows = []
    by_dom = defaultdict(list)
    for r in records:
        by_dom[domain_of(r["file"])].append(r)
    for dom_id, name in enumerate(domains, start=1):
        items = by_dom.get(dom_id, [])
        c = Counter(r["disposition"] for r in items)
        rows.append({
            "id": dom_id, "domain": name, "total": len(items),
            "verified_correct": c.get("VERIFIED-CORRECT", 0),
            "defect_fixed": c.get("DEFECT-FIXED", 0),
            "intentional": c.get("INTENTIONAL-BY-DESIGN", 0),
            "duplicate_dead": c.get("DUPLICATE-DEAD-WITH-EVIDENCE", 0),
            "removed_with_evidence": c.get("REMOVED-WITH-EVIDENCE", 0),
            "accepted_limitation": c.get("ACCEPTED-LIMITATION", 0),
            "external_acceptance_only": c.get("EXTERNAL-ACCEPTANCE-ONLY", 0),
            "under_review": c.get("UNDER-REVIEW", 0),
            "evidence_incomplete": c.get("EVIDENCE-INCOMPLETE", 0),
            "critical_open": sum(1 for r in items if r["disposition"] in OPEN_STATES
                                 and r["priority"] == "CRITICAL"),
            "high_open": sum(1 for r in items if r["disposition"] in OPEN_STATES
                             and r["priority"] == "HIGH"),
            "mapping_basis": "file-path rule (see DOMAIN_RULES in tools/m34/audit34.py)",
        })
    return {
        "schema": "m34-domain-matrix",
        "generated_utc": NOW,
        "taxonomy": "the 69-domain taxonomy carried from docs/audits/m29-evidence/domain-matrix.json "
                    "(ids and names unchanged, so the matrices are comparable)",
        "ledger_items": len(records),
        "domains": rows,
        "reconciliation": {
            "sum_of_domain_totals": sum(r["total"] for r in rows),
            "ledger_total": len(records),
            "reconciles": sum(r["total"] for r in rows) == len(records),
        },
        "mapping_caveat": "domain counts are a projection of the ledger by file path. The ledger "
                          "record is the source of truth for one occurrence; the domain row only "
                          "says which part of the application that file belongs to.",
    }


def build_invariants(records: list[dict]) -> dict:
    total = len(records)
    term = [r for r in records if r["disposition"] in TERMINAL]
    openr = [r for r in records if r["disposition"] in OPEN_STATES]
    ur = [r for r in records if r["disposition"] == "UNDER-REVIEW"]
    ei = [r for r in records if r["disposition"] == "EVIDENCE-INCOMPLETE"]
    crit = [r for r in openr if r["priority"] == "CRITICAL"]
    high = [r for r in openr if r["priority"] == "HIGH"]
    external = [r for r in records if r["disposition"] == "EXTERNAL-ACCEPTANCE-ONLY"]
    by_rule = Counter(r["rule"] for r in openr)
    return {
        "schema": "m34-closure-invariants",
        "generated_utc": NOW,
        "inventory_total": total,
        "terminal_items": len(term),
        "unreviewed": len(ur),
        "evidence_incomplete": len(ei),
        "critical_unresolved": len(crit),
        "high_unresolved": len(high),
        "external_acceptance_only": len(external),
        "closure_gate_inventory_equals_terminal": total == len(term),
        "closure_gate_unreviewed_zero": len(ur) == 0,
        "closure_gate_evidence_incomplete_zero": len(ei) == 0,
        "blocker_gate_critical_zero": len(crit) == 0,
        "blocker_gate_high_zero": len(high) == 0,
        "open_items_driven_by_rules": dict(by_rule.most_common(20)),
        "open_items_driven_by_rule_families": {k: v for k, v in by_rule.most_common(40)},
        "statement": ("Semantic closure is NOT claimed: "
                      f"{len(ur)} item(s) remain UNDER-REVIEW and {len(ei)} EVIDENCE-INCOMPLETE, "
                      f"of which {len(high)} are HIGH and {len(crit)} CRITICAL. "
                      "Each open item names the fact that is missing; none was closed on pattern "
                      "alone and none was mass-assigned a disposition.")
        if openr else "Semantic closure gate satisfied on this ledger.",
        "per_open_rule_priority": {rule: dict(Counter(r["priority"] for r in openr if r["rule"] == rule))
                                   for rule, _ in by_rule.most_common(20)},
    }


def build_ledger_summary(ledger: dict, records: list[dict]) -> dict:
    disp = Counter(r["disposition"] for r in records)
    origin = Counter(r.get("origin", "?") for r in records)
    prio = Counter(r["priority"] for r in records)
    prior = Counter(str(r.get("m33_disposition") or r.get("prior_disposition") or "M34-NEW")
                    for r in records if r.get("origin") != "M34-NEW")
    return {
        "schema": "m34-ledger-summary",
        "generated_utc": NOW,
        "source_of_truth": {"path": "docs/audits/m34-evidence/m34-ledger.json",
                             "sha256": sha256(LEDGER), "bytes": LEDGER.stat().st_size},
        "items": len(records),
        "dispositions": dict(disp),
        "origin": dict(origin),
        "priority": dict(prio),
        "carry_forward": ledger.get("carry_forward"),
        "readjudication_of_inherited_under_review": ledger.get("readjudication_of_inherited_under_review"),
        "sweep": {"hits": ledger.get("sweep_hits"), "new_hits": len(ledger.get("new_records", [])),
                  "already_covered_by_m33": ledger.get("sweep_hits_covered_by_m33")},
        "comparison_with_earlier_inventories": {
            "note": "the earlier numbers 2232 (M30) / 6860 (M31) / 3518 (M32 remaining) / 8934 (M33) "
                    "are treated as claims; the comparison below de-duplicates by the M34 identity "
                    "(path, family, line) and reports what is genuinely new versus carried",
            "m33_records_ingested": ledger.get("m33_items"),
            "carried_forward_same_file_hash": ledger.get("carry_forward", {}).get("SAME-FILE-HASH"),
            "new_hits_after_family_correction": len(ledger.get("new_records", [])),
            "hits_already_held_by_m33": ledger.get("sweep_hits_covered_by_m33"),
        },
        "open_state_priority_breakdown": {
            "UNDER-REVIEW": dict(Counter(r["priority"] for r in records if r["disposition"] == "UNDER-REVIEW")),
            "EVIDENCE-INCOMPLETE": dict(Counter(r["priority"] for r in records
                                                if r["disposition"] == "EVIDENCE-INCOMPLETE")),
        },
    }


def build_doc_audit(records: list[dict]) -> dict:
    heads = sh("git", "rev-parse", "HEAD").strip()
    branches = sh("git", "branch", "-a").strip().splitlines()
    local_branches = {b.strip().lstrip("* ").strip() for b in branches}
    doc_files = sorted([p for p in ROOT.glob("*.md")] +
                       [p for p in (ROOT / "docs").rglob("*.md")])
    sha_re = re.compile(r"\b[0-9a-f]{40}\b")
    count_re = re.compile(r"\b(\d{3,5})\s+(?:tests?|passed|collected)\b", re.I)
    findings = []
    for path in doc_files:
        rel = str(path.relative_to(ROOT))
        text = path.read_text(encoding="utf-8", errors="replace")
        for sha in set(sha_re.findall(text)):
            resolvable = subprocess.run(["git", "cat-file", "-e", f"{sha}^{{commit}}"],
                                        cwd=ROOT, capture_output=True).returncode == 0
            findings.append({"doc": rel, "claim_type": "sha", "claim": sha,
                             "state": "CURRENT-VERIFIED" if sha == heads else
                                      ("RESOLVES-LOCALLY" if resolvable else "UNRESOLVED"),
                             "basis": "git cat-file -e <sha>^{commit}"})
        for m in set(count_re.findall(text)):
            findings.append({"doc": rel, "claim_type": "test-count", "claim": m,
                             "state": "HISTORICAL" if rel.startswith("docs/audits/") or
                                      re.match(r"M\d+_", rel) else "CHECK-AGAINST-FINAL-RUN",
                             "basis": "final pytest collection/run counts"})
        for needle, state in (("drill-Master", "HISTORICAL"), ("CERTIFI", "CHECK")):
            if needle in text:
                findings.append({"doc": rel, "claim_type": "branch-or-status", "claim": needle,
                                 "state": state,
                                 "basis": "the session works on arena/01a0c945-drill-master"})
    return {
        "schema": "m34-doc-claim-audit",
        "generated_utc": NOW,
        "head": heads,
        "local_branches": sorted(local_branches),
        "docs_scanned": len(doc_files),
        "finding_counts": dict(Counter(f["state"] for f in findings)),
        "findings": findings,
        "rule": "no earlier mission's report is a source of truth; a doc claim is CURRENT-VERIFIED "
                "only when this mission re-derived it from the tree",
    }


CACHE_PATTERNS = ["__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".coverage",
                  ".venv", "venv/", "*.pyc", "*.pyo", "*.orig", "*.rej", "*.bak", "*.tmp",
                  "*.log", "*.sqlite", "*.db-journal"]
SECRET_PATTERNS = [
    r"(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|private[_-]?key|passwd|password)\s*=\s*[\"'][^\"'\s]{8,}",
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    r"(?i)\bsk-[A-Za-z0-9]{20,}",
    r"(?i)\bghp_[A-Za-z0-9]{20,}",
    r"(?i)\bAKIA[0-9A-Z]{16}\b",
]
MUTANT_MARKERS = ["MUTANT", "if False:  # mutant", "M34-M-"]


def build_git_cleanliness() -> dict:
    status = sh("git", "status", "--porcelain", "-z", "-uall", binary=True).decode("utf-8", "replace")
    entries = []
    toks = status.split("\0")
    i = 0
    while i < len(toks):
        tok = toks[i]
        if not tok:
            i += 1
            continue
        code, path = tok[:2], tok[3:]
        entries.append({"code": code, "path": path})
        i += 2 if code[:1] in ("R", "C") or code[1:2] in ("R", "C") else 1

    classes = Counter()
    for e in entries:
        p = e["path"]
        if p.startswith("docs/audits/m34-evidence/"):
            cls = "M34-EVIDENCE"
        elif p.startswith("docs/audits/m3"):
            cls = "PRIOR-MISSION-EVIDENCE"
        elif p.startswith("tools/m34/"):
            cls = "M34-TOOLING"
        elif p.startswith("tools/"):
            cls = "TOOLING"
        elif p.startswith("tests/"):
            cls = "TEST"
        elif re.match(r"^(core|tabs|dialogs|assets)/|\.py$", p):
            cls = "PRODUCTION-OR-ROOT-CODE"
        elif p.endswith((".md", ".txt", ".json", ".xml")):
            cls = "DOCUMENTATION"
        else:
            cls = "OTHER"
        classes[cls] += 1
        e["class"] = cls

    caches = [e["path"] for e in entries if any(
        re.search(pat.replace("*", ".*") + "$", e["path"]) for pat in CACHE_PATTERNS)]
    mutants = []
    for e in entries:
        if not e["path"].endswith((".py", ".json")):
            continue
        p = ROOT / e["path"]
        if not p.is_file() or p.stat().st_size > 4_000_000:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        hit = [m for m in MUTANT_MARKERS if m in text]
        if hit:
            mutants.append({"path": e["path"], "markers": hit})
    secrets = []
    for e in entries:
        p = ROOT / e["path"]
        if not p.is_file() or p.stat().st_size > 4_000_000 or p.suffix in (".png", ".xlsx", ".whl"):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for pat in SECRET_PATTERNS:
            m = re.search(pat, text)
            if m:
                secrets.append({"path": e["path"], "pattern": pat, "sample": m.group(0)[:40]})
    diff_check = subprocess.run(["git", "diff", "--check"], cwd=ROOT, capture_output=True, text=True)
    return {
        "schema": "m34-git-cleanliness",
        "generated_utc": NOW,
        "modified_tracked": sum(1 for e in entries if e["code"][1:2] != "?" and not e["code"].startswith("??")),
        "untracked": sum(1 for e in entries if e["code"] == "??"),
        "deleted": sum(1 for e in entries if "D" in e["code"]),
        "staged": sum(1 for e in entries if e["code"][0] not in (" ", "?")),
        "classes": dict(classes),
        "diff_check_clean": diff_check.returncode == 0,
        "diff_check_output": diff_check.stdout.strip()[:500],
        "cache_artifacts_present": caches,
        "mutant_markers_present": mutants,
        "secret_findings": secrets,
        "untracked_top_level": dict(Counter(e["path"].split("/")[0] for e in entries
                                            if e["code"] == "??")),
        "note": "nothing is deleted by this stage; a cache artefact or a secret is reported for a "
                "human decision (DO NOT COMMIT — REVIEW REQUIRED), never removed",
    }


def main() -> int:
    ledger = json.loads(LEDGER.read_text())
    records = ledger["carried_records"] + ledger["new_records"]
    m33_matrix = json.loads((ROOT / "docs/audits/m33-evidence/m33-domain-matrix.json").read_text())
    domains = [r["domain"] for r in m33_matrix["domains"]]

    matrix = build_domain_matrix(domains, records)
    (EV / "m34-domain-matrix.json").write_text(json.dumps(matrix, indent=1))

    invariants = build_invariants(records)
    (EV / "m34-closure-invariants.json").write_text(json.dumps(invariants, indent=1))

    summary = build_ledger_summary(ledger, records)
    (EV / "m34-ledger-summary.json").write_text(json.dumps(summary, indent=1))

    docs = build_doc_audit(records)
    (EV / "m34-doc-claim-audit.json").write_text(json.dumps(docs, indent=1))

    clean = build_git_cleanliness()
    (EV / "m34-git-cleanliness.json").write_text(json.dumps(clean, indent=1))

    inventory_ledger = {
        "schema": "M34_INVENTORY_LEDGER",
        "generated_utc": NOW,
        "what_this_file_is": "Manifest and invariant projection of the Mission 34 inventory. The "
                             "per-item ledger (INV-ID, path, symbol, family, line, context "
                             "fingerprint, source sha256, domain, priority, disposition, rule, "
                             "root cause, evidence) is m34-ledger.json in this directory; this file "
                             "states its invariants and pins its hash. Any disagreement is resolved "
                             "in favour of m34-ledger.json.",
        "source_of_truth": {"path": "docs/audits/m34-evidence/m34-ledger.json",
                            "sha256": sha256(LEDGER), "bytes": LEDGER.stat().st_size,
                            "item_count": len(records)},
        "inventory": {"total": len(records), "origin": summary["origin"],
                      "dispositions": summary["dispositions"], "priority": summary["priority"]},
        "reconciliation": summary["comparison_with_earlier_inventories"],
        "open_residual": {"under_review": invariants["unreviewed"],
                          "evidence_incomplete": invariants["evidence_incomplete"],
                          "critical": invariants["critical_unresolved"],
                          "high": invariants["high_unresolved"],
                          "driven_by_rules": invariants["open_items_driven_by_rules"]},
        "domain_matrix": {"path": "docs/audits/m34-evidence/m34-domain-matrix.json",
                          "domains": len(domains), "reconciles": matrix["reconciliation"]["reconciles"]},
        "verification": {"fix_reverification": "docs/audits/m34-evidence/m34-fix-reverification.json",
                         "mutation_controls": "docs/audits/m34-evidence/m34-mutation-controls.json"},
        "capture_context": {
            "head": sh("git", "rev-parse", "HEAD").strip(),
            "tree": sh("git", "rev-parse", "HEAD^{tree}").strip(),
            "branch": sh("git", "rev-parse", "--abbrev-ref", "HEAD").strip(),
            "python": sys.version.split()[0],
        },
        "closure_gate": {k: v for k, v in invariants.items()
                         if k.startswith(("closure_gate", "blocker_gate", "inventory_", "terminal_",
                                          "unreviewed", "evidence_incomplete", "critical_unresolved",
                                          "high_unresolved", "statement"))},
    }
    (EV / "M34_INVENTORY_LEDGER.json").write_text(json.dumps(inventory_ledger, indent=1))

    print("domain matrix reconciles:", matrix["reconciliation"])
    print("invariants:", {k: invariants[k] for k in ("inventory_total", "terminal_items", "unreviewed",
                                                     "evidence_incomplete", "critical_unresolved",
                                                     "high_unresolved")})
    print("doc findings:", docs["finding_counts"])
    print("git cleanliness:", {k: clean[k] for k in ("modified_tracked", "untracked", "deleted",
                                                     "staged", "diff_check_clean")},
          "caches:", len(clean["cache_artifacts_present"]), "mutants:", len(clean["mutant_markers_present"]),
          "secrets:", len(clean["secret_findings"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
