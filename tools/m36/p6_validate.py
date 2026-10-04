#!/usr/bin/env python3
"""Read-only M36/P6 accounting, batch, and provenance reconciliation.

Run the structural checks in any checkout with:
    python tools/m36/p6_validate.py

For Git-history/source-hash verification (requires the relevant historical commits locally):
    python tools/m36/p6_validate.py --verify-git-history

The command prints a JSON summary to stdout; it does not modify batch evidence, register, or ledger.
Missing historical source hashes are reported as provenance gaps rather than silently accepted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.m36.p6_apply import calculate_accounting

EVIDENCE = ROOT / "docs/audits/m36-evidence"
CROSS_LINK_COMMITS = {
    "INV34-002162": "e6a1ffb23a7641d09ad0a94e693b879de45ec612",
    "INV34-005709": "6c07d3a2ed4782bb5dd707f43b0d78635dead162",
    "INV34-006841": "dc0ad4b08e3c94bf87419114aa55c74c450dd8f3",
}


def _git(*args: str, check: bool = True) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return result.stdout.strip()


def _canonical_commit(revision: str) -> str | None:
    try:
        return _git("rev-parse", "--verify", f"{revision}^{{commit}}")
    except RuntimeError:
        return None


def _verify_source_hash(evidence_commit: str, path: str, expected_sha256: str,
                        version_cache: dict) -> tuple[str, str | None, bytes | None]:
    key = (evidence_commit, path)
    if key not in version_cache:
        revs = _git("rev-list", "--full-history", evidence_commit, "--", path).splitlines()
        candidates = {evidence_commit}
        for revision in revs:
            candidates.add(revision)
            candidates.update(_git("show", "-s", "--format=%P", revision).split())
        matches: dict[str, tuple[str, bytes]] = {}
        for revision in candidates:
            result = subprocess.run(["git", "show", f"{revision}:{path}"], cwd=ROOT,
                                    capture_output=True)
            if result.returncode:
                continue
            blob = result.stdout
            matches.setdefault(hashlib.sha256(blob).hexdigest(), (revision, blob))
        version_cache[key] = matches
    value = version_cache[key].get(expected_sha256)
    if value is None:
        return "NOT_FOUND_IN_AVAILABLE_ANCESTRY", None, None
    return "MATCHED", value[0], value[1]


def reconcile(verify_git_history: bool = False) -> dict:
    register = json.loads((EVIDENCE / "m36-open-item-register.json").read_text(encoding="utf-8"))
    ledger = json.loads((EVIDENCE / "m36-master-ledger.json").read_text(encoding="utf-8"))
    by_id = {record["id"]: record for record in register["records"]}
    ledger_batches = {batch["batch"]: batch for batch in ledger.get("batches", [])}
    expected_names = [f"p6-batch-{number:03d}" for number in range(2, 30)]
    errors: list[str] = []
    batch_ids: list[str] = []
    source_sites: dict[tuple[str, int], list[tuple[str, str]]] = defaultdict(list)
    new_finding_ids: list[str] = []
    class_totals: Counter = Counter()
    source_hash_result: Counter = Counter()
    prefix_line_matches: list[dict] = []
    missing_source_hashes: list[dict] = []
    fixed_anchor_gaps: list[dict] = []
    version_cache: dict = {}
    git_summary = {"verified_evidence_commits": 0, "verified_heads": 0,
                   "verified_production_commits": 0, "verified_payload_latest_commits": 0,
                   "verified_supplemental_test_evidence_commits": 0}

    if len(ledger_batches) != 28 or set(ledger_batches) != set(expected_names):
        errors.append("ledger batch list is not exactly p6-batch-002 through p6-batch-029")

    for name in expected_names:
        payload_path = EVIDENCE / f"{name}.json"
        if not payload_path.is_file() or name not in ledger_batches:
            errors.append(f"missing payload or ledger summary for {name}")
            continue
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        summary = ledger_batches[name]
        items = payload.get("items", [])
        item_ids = [item.get("id") for item in items]
        if len(item_ids) != len(set(item_ids)):
            errors.append(f"duplicate item IDs in {name}")
        batch_ids.extend(item_ids)
        counts = Counter(item.get("classification") for item in items)
        class_totals.update(counts)
        site_count = len({(item.get("file"), item.get("line")) for item in items})
        if payload.get("records") != len(items) or summary.get("records") != len(items):
            errors.append(f"record count mismatch in {name}")
        if payload.get("sites") != site_count or summary.get("sites") != site_count:
            errors.append(f"site count mismatch in {name}")
        if payload.get("by_classification") != dict(counts):
            errors.append(f"payload classification count mismatch in {name}")
        if summary.get("by_classification") != dict(counts):
            errors.append(f"ledger classification count mismatch in {name}")
        if summary.get("tests") != payload.get("tests"):
            errors.append(f"test evidence mismatch in {name}")
        if summary.get("defects_fixed") != payload.get("defects_fixed", []):
            errors.append(f"defect-fix evidence mismatch in {name}")
        if summary.get("head") != payload.get("head"):
            errors.append(f"source head mismatch in {name}")
        stale = payload.get("staleness", {})
        if stale.get("checked") != len(items):
            errors.append(f"staleness checked count mismatch in {name}")

        for item in items:
            ident = item.get("id")
            record = by_id.get(ident)
            if record is None:
                errors.append(f"{name}/{ident}: absent from master register")
                continue
            source_sites[(item.get("file"), item.get("line"))].append((name, ident))
            if record.get("p6_batch") != name:
                errors.append(f"{name}/{ident}: p6_batch assignment mismatch")
            for key, field in (("classification", "classification"),
                                ("evidence", "p6_evidence"),
                                ("remaining_question", "p6_remaining_question")):
                if record.get(field) != item.get(key):
                    errors.append(f"{name}/{ident}: {field} differs from payload")
            if record.get("p6_defect") != bool(item.get("defect")):
                errors.append(f"{name}/{ident}: defect flag differs from payload")
            expected_commit = item.get("commit") or payload.get("commit")
            for fix in payload.get("defects_fixed", []):
                if isinstance(fix, dict) and (fix.get("id") == ident or ident in (fix.get("records") or [])):
                    expected_commit = expected_commit or fix.get("fix_commit") or fix.get("commit")
            expected_commit = expected_commit or CROSS_LINK_COMMITS.get(ident)
            actual_commit = record.get("p6_commit")
            if expected_commit and (not actual_commit or not (
                    actual_commit.startswith(expected_commit) or expected_commit.startswith(actual_commit))):
                errors.append(f"{name}/{ident}: p6_commit does not match evidence")
            if actual_commit and not expected_commit and ident not in CROSS_LINK_COMMITS:
                errors.append(f"{name}/{ident}: unsubstantiated p6_commit stamp")
            for key in ("file", "line", "symbol", "rule", "kind"):
                if key in item and record.get(key) != item.get(key):
                    errors.append(f"{name}/{ident}: source field {key} differs")
            if "register_line_text" in item and record.get("current_source_line") != item["register_line_text"]:
                errors.append(f"{name}/{ident}: original source line differs")
            site = item.get("site")
            if site:
                pairs = (("file", "file"), ("line", "line"), ("symbol", "symbol"),
                         ("expression", "current_source_line"),
                         ("source_sha256", "source_sha256"),
                         ("context_fingerprint", "context_fingerprint"))
                for item_key, record_key in pairs:
                    if site.get(item_key) != record.get(record_key):
                        errors.append(f"{name}/{ident}: site provenance {item_key} differs")

        findings = payload.get("new_findings", [])
        new_finding_ids.extend(finding.get("id") for finding in findings)
        if [finding.get("id") for finding in summary.get("new_findings", [])] != [
                finding.get("id") for finding in findings]:
            errors.append(f"secondary finding IDs mismatch in {name}")

        if verify_git_history:
            payload_relpath = f"docs/audits/m36-evidence/{name}.json"
            latest_payload = summary.get("payload_latest_commit")
            latest_resolved = _canonical_commit(latest_payload or "")
            actual_latest = _git("log", "-1", "--format=%H", "--", payload_relpath)
            if not latest_resolved or latest_resolved != latest_payload or latest_payload != actual_latest:
                errors.append(f"{name}: payload latest-commit stamp differs from Git path history")
            else:
                git_summary["verified_payload_latest_commits"] += 1
            evidence_commit = summary.get("evidence_commit")
            evidence_commit_full = _canonical_commit(evidence_commit or "")
            if not evidence_commit_full:
                errors.append(f"{name}: evidence commit does not resolve")
            elif evidence_commit_full != evidence_commit:
                errors.append(f"{name}: evidence commit is not stored as a full SHA")
            else:
                check = subprocess.run(["git", "merge-base", "--is-ancestor", evidence_commit_full, "HEAD"],
                                       cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if check.returncode:
                    errors.append(f"{name}: evidence commit is not an ancestor of HEAD")
                else:
                    path = f"docs/audits/m36-evidence/{name}.json"
                    if subprocess.run(["git", "cat-file", "-e", f"{evidence_commit_full}:{path}"],
                                      cwd=ROOT, stderr=subprocess.DEVNULL).returncode:
                        errors.append(f"{name}: payload absent from evidence commit")
                    else:
                        git_summary["verified_evidence_commits"] += 1
            head = summary.get("head_commit")
            if head:
                resolved_head = _canonical_commit(head)
                if not resolved_head or resolved_head != head:
                    errors.append(f"{name}: normalized source head does not resolve")
                else:
                    expected_tree = _git("rev-parse", f"{head}^{{tree}}")
                    if summary.get("source_tree") != expected_tree:
                        errors.append(f"{name}: source tree hash mismatch")
                    else:
                        git_summary["verified_heads"] += 1
            elif payload.get("head") is not None:
                errors.append(f"{name}: recorded head was not normalized")
            for fix in summary.get("production_commits", []):
                commit = _canonical_commit(fix.get("sha", ""))
                if not commit or commit != fix.get("sha"):
                    errors.append(f"{name}: production/test commit does not resolve")
                elif subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"],
                                    cwd=ROOT).returncode:
                    errors.append(f"{name}: production/test commit is not an ancestor")
                else:
                    git_summary["verified_production_commits"] += 1
            supplemental = summary.get("supplemental_test_evidence_commits", [])
            gate = payload.get("tests", {}).get("source_release_gate") if isinstance(payload.get("tests"), dict) else None
            if gate and not supplemental:
                errors.append(f"{name}: supplemental source-release-gate evidence commit is missing")
            for evidence in supplemental:
                commit = _canonical_commit(evidence.get("sha", ""))
                if not commit or commit != evidence.get("sha"):
                    errors.append(f"{name}: supplemental evidence commit does not resolve")
                elif subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"],
                                    cwd=ROOT).returncode:
                    errors.append(f"{name}: supplemental evidence commit is not an ancestor")
                else:
                    committed_payload = subprocess.run(
                        ["git", "show", f"{commit}:{payload_relpath}"], cwd=ROOT,
                        capture_output=True, text=True,
                    )
                    if committed_payload.returncode:
                        errors.append(f"{name}: supplemental commit lacks batch payload")
                    else:
                        committed_data = json.loads(committed_payload.stdout)
                        committed_gate = committed_data.get("tests", {}).get("source_release_gate", {})
                        if (not committed_gate or committed_gate.get("commit_checked") != evidence.get("commit_checked")
                                or committed_gate.get("result") != evidence.get("result")):
                            errors.append(f"{name}: supplemental commit does not contain the recorded gate result")
                        else:
                            git_summary["verified_supplemental_test_evidence_commits"] += 1

            if not evidence_commit_full:
                continue

            # Check each original source-file digest against a version in this batch's evidence
            # ancestry. One recorded line is known to be truncated at its source-register limit;
            # its exact source file hash and line prefix are still checked here.
            file_hashes = {(record.get("file"), record.get("source_sha256"))
                           for item in items if (record := by_id.get(item.get("id")))
                           if record.get("file") and record.get("source_sha256")}
            for file_path, digest in file_hashes:
                state, revision, blob = _verify_source_hash(
                    evidence_commit_full, file_path, digest, version_cache)
                source_hash_result[state] += 1
                if state != "MATCHED":
                    missing_source_hashes.append({"batch": name, "file": file_path,
                                                  "sha256": digest,
                                                  "record_ids": sorted(item.get("id") for item in items
                                                                       if (record := by_id.get(item.get("id")))
                                                                       and record.get("file") == file_path
                                                                       and record.get("source_sha256") == digest),
                                                  "status": state})
                    continue
                # At a verified exact-file version, line content is checked by the record anchor.
                lines = blob.decode("utf-8", "replace").splitlines()
                for item in items:
                    record = by_id.get(item.get("id"))
                    if not record or record.get("file") != file_path or record.get("source_sha256") != digest:
                        continue
                    line_number = record.get("line")
                    expected_line = record.get("current_source_line") or ""
                    if not isinstance(line_number, int) or not 1 <= line_number <= len(lines):
                        errors.append(f"{name}/{record['id']}: original source line is out of range")
                    elif lines[line_number - 1].strip() == expected_line.strip():
                        continue
                    elif expected_line.strip() and lines[line_number - 1].strip().startswith(expected_line.strip()):
                        prefix_line_matches.append({"batch": name, "id": record["id"],
                                                    "file": file_path, "line": line_number,
                                                    "matched_commit": revision})
                    else:
                        errors.append(f"{name}/{record['id']}: line does not match verified source hash")

    if verify_git_history:
        fixed_records = [record for record in register["records"]
                         if record.get("classification") == "DEFECT-FIXED"]
        fixed_groups = {(record.get("fixed_commit"), record.get("file"), record.get("source_sha256"))
                         for record in fixed_records}
        for fixed_commit, file_path, digest in fixed_groups:
            fixed_full = _canonical_commit(fixed_commit or "")
            if not fixed_full:
                errors.append("pre-P6 DEFECT-FIXED commit does not resolve")
                continue
            before_fix = _git("rev-parse", f"{fixed_full}^")
            state, revision, _blob = _verify_source_hash(before_fix, file_path, digest, version_cache)
            if state != "NOT_FOUND_IN_AVAILABLE_ANCESTRY":
                errors.append("pre-P6 source-hash availability differs from the recorded provenance gap")
            fixed_anchor_gaps.append({
                "file": file_path, "source_sha256": digest,
                "record_ids": sorted(record["id"] for record in fixed_records
                                      if record.get("fixed_commit") == fixed_commit
                                      and record.get("file") == file_path
                                      and record.get("source_sha256") == digest),
                "fixed_commit": fixed_full, "status": state,
            })
        recorded_source = ledger.get("source_hash_reconciliation", {})
        recorded_gaps = {(item.get("batch"), item.get("file"), item.get("source_sha256"),
                          tuple(sorted(item.get("record_ids", []))))
                         for item in recorded_source.get("unmatched_contexts", [])}
        actual_gaps = {(item.get("batch"), item.get("file"), item.get("sha256"),
                        tuple(sorted(item.get("record_ids", []))))
                       for item in missing_source_hashes}
        if recorded_gaps != actual_gaps:
            errors.append("recorded batch source-hash gaps differ from Git-history verification")
        recorded_fixed = recorded_source.get("pre_p6_fixed_source_anchor", {})
        if fixed_anchor_gaps and (
                recorded_fixed.get("status") != fixed_anchor_gaps[0]["status"]
                or set(recorded_fixed.get("record_ids", [])) != set(fixed_anchor_gaps[0]["record_ids"])
                or recorded_fixed.get("fixed_commit") != fixed_anchor_gaps[0]["fixed_commit"]
                or recorded_fixed.get("source_sha256") != fixed_anchor_gaps[0]["source_sha256"]):
            errors.append("recorded pre-P6 source-hash gap differs from Git-history verification")

    duplicate_register_ids = len(batch_ids) - len(set(batch_ids))
    if duplicate_register_ids:
        errors.append(f"{duplicate_register_ids} register IDs appear in multiple batch payloads")
    if set(batch_ids) != {record.get("id") for record in by_id.values()
                          if record.get("p6_batch", "").startswith("p6-batch-")}:
        errors.append("batch payload IDs do not exactly cover register batch assignments")
    if set(new_finding_ids) & set(by_id):
        errors.append("secondary NEW-P6 finding ID overlaps the original register")
    if len(new_finding_ids) != len(set(new_finding_ids)):
        errors.append("secondary NEW-P6 IDs are duplicated")
    secondary_summary = ledger.get("secondary_finding_summary", {})
    if secondary_summary.get("count") != len(new_finding_ids) or set(secondary_summary.get("ids", [])) != set(new_finding_ids):
        errors.append("secondary finding summary differs from batch payloads")
    owner_ids = {"NEW-P6-007", "NEW-P6-008", "NEW-P6-015", "NEW-P6-020", "NEW-P6-023", "NEW-P6-024"}
    w15_path = EVIDENCE / "p6-remediation-w15-2026-09-30.json"
    if not w15_path.is_file():
        errors.append("W15 owner-decision evidence is missing")
    else:
        w15 = json.loads(w15_path.read_text(encoding="utf-8"))
        w15_findings = {item.get("id"): item.get("status") for item in w15.get("findings", [])}
        if set(w15_findings) != owner_ids:
            errors.append("W15 owner-decision findings differ from the six preserved IDs")
        if secondary_summary.get("owner_decision_findings_open") != w15_findings:
            errors.append("ledger owner-decision summary differs from W15 statuses")
    for bundle in ledger.get("recovery_bundles", []):
        if bundle.get("current_verification_status") != "NOT_VERIFIED":
            errors.append("recovery bundle is presented as currently verified without current evidence")

    accounting = calculate_accounting(register, ledger.get("batches", []))
    if not accounting["check"]:
        errors.extend(accounting["errors"])
    stored = ledger.get("arithmetic", {})
    for key in ("register_records_at_p6_start", "pre_p6_defect_fixed_records",
                "open_records_at_p6_start", "adjudicated_by_p6_batches", "current_open"):
        if stored.get(key) != accounting.get(key):
            errors.append(f"ledger arithmetic field {key} is stale or mislabeled")

    defect_fix = ledger.get("defect_fix_reconciliation", {})
    genuine_ids = {record["id"] for record in register["records"]
                   if record.get("classification") == "GENUINE_DEFECT"}
    mapped = set(defect_fix.get("by_record", {}))
    if genuine_ids != mapped:
        errors.append("GENUINE_DEFECT register records are not all mapped to fix evidence")
    for ident in genuine_ids:
        fix = defect_fix.get("by_record", {}).get(ident, {})
        if fix.get("fix_commit") != by_id[ident].get("p6_commit"):
            errors.append(f"{ident}: fix crosswalk commit differs from register p6_commit")

    repeated_sites = {site: rows for site, rows in source_sites.items() if len(rows) > 1}
    cross_batch_sites = {site: rows for site, rows in repeated_sites.items()
                         if len({batch for batch, _ in rows}) > 1}
    source_overlap = {
        "repeated_file_line_groups": len(repeated_sites),
        "additional_record_occurrences_at_repeated_sites": sum(len(rows) - 1 for rows in repeated_sites.values()),
        "repeated_sites_across_batches": len(cross_batch_sites),
        "additional_records_at_cross_batch_sites": sum(len(rows) - 1 for rows in cross_batch_sites.values()),
        "record_id_overlap": duplicate_register_ids,
        "meaning": "Repeated source locations are not duplicate record IDs; per-batch site counts are local distinct file/line pairs, not additive global sites.",
    }
    recorded_overlap = ledger.get("source_site_overlap_summary", {})
    overlap_fields = ("repeated_file_line_groups_within_or_across_batches",
                      "additional_records_at_repeated_file_line_groups",
                      "repeated_file_line_groups_spanning_multiple_batches",
                      "additional_records_at_cross_batch_file_line_groups",
                      "record_id_overlap_across_batches")
    computed_overlap = (len(repeated_sites),
                        sum(len(rows) - 1 for rows in repeated_sites.values()),
                        len(cross_batch_sites),
                        sum(len(rows) - 1 for rows in cross_batch_sites.values()),
                        duplicate_register_ids)
    if recorded_overlap and (
            tuple(recorded_overlap.get(field) for field in overlap_fields) != computed_overlap
            or recorded_overlap.get("batch_item_ids_unique") != (duplicate_register_ids == 0)):
        errors.append("recorded source-site overlap summary differs from batch payloads")

    recorded_hash_summary = ledger.get("source_hash_reconciliation", {})
    matched_hash_contexts = source_hash_result.get("MATCHED", 0)
    source_context_total = matched_hash_contexts + len(missing_source_hashes)
    if verify_git_history and recorded_hash_summary:
        if recorded_hash_summary.get("batch_file_hash_contexts_checked") != source_context_total:
            errors.append("recorded source-hash context count differs from Git-history verification")
        if recorded_hash_summary.get("batch_file_hash_contexts_matched_in_available_evidence_ancestry") != matched_hash_contexts:
            errors.append("recorded matched source-hash count differs from Git-history verification")
        recorded_prefix = recorded_hash_summary.get("truncated_source_line_prefix_match", {})
        if prefix_line_matches and (
                recorded_prefix.get("batch") != prefix_line_matches[0].get("batch")
                or recorded_prefix.get("record_id") != prefix_line_matches[0].get("id")
                or recorded_prefix.get("file") != prefix_line_matches[0].get("file")
                or recorded_prefix.get("line") != prefix_line_matches[0].get("line")):
            errors.append("recorded truncated-line prefix exception differs from Git-history verification")

    source_status = "NOT_RUN"
    has_source_gaps = bool(missing_source_hashes or fixed_anchor_gaps)
    if verify_git_history:
        source_status = "PARTIAL" if has_source_gaps else "PASS"
    overall = "FAIL" if errors else ("PARTIAL" if verify_git_history and has_source_gaps else "PASS")
    return {
        "overall": overall,
        "structural_checks": "PASS" if not errors else "FAIL",
        "git_history_checks": "PASS" if verify_git_history and not errors else ("PARTIAL" if verify_git_history else "NOT RUN"),
        "source_hash_checks": source_status,
        "register": {
            "records": len(register["records"]),
            "pre_p6_defect_fixed": accounting["pre_p6_defect_fixed_records"],
            "p6_batch_adjudicated": accounting["adjudicated_by_p6_batches"],
            "current_open": accounting["current_open"],
            "classification_totals": dict(Counter(r.get("classification") for r in register["records"])),
        },
        "batches": {"count": len(ledger_batches), "item_records": len(batch_ids),
                    "unique_item_ids": len(set(batch_ids)), "classification_totals": dict(class_totals),
                    "source_overlap": source_overlap},
        "secondary_new_findings": {"count": len(new_finding_ids),
                                    "unique_ids": len(set(new_finding_ids)),
                                    "overlaps_register": bool(set(new_finding_ids) & set(by_id))},
        "defect_fix_reconciliation": {"genuine_defect_records": len(genuine_ids),
                                      "mapped_records": len(mapped),
                                      "batch_fix_entries": defect_fix.get("batch_defects_fixed_entries"),
                                      "cross_linked_records": len(defect_fix.get("cross_linked_through_secondary_finding", []))},
        "git_history": git_summary if verify_git_history else None,
        "source_hash_reconciliation": {
            "batch_file_hash_contexts_checked": source_context_total,
            "verified_batch_file_hash_pairs": matched_hash_contexts,
            "not_found_in_available_ancestry": missing_source_hashes,
            "pre_p6_fixed_source_anchors": fixed_anchor_gaps if verify_git_history else None,
            "truncated_source_line_prefix_matches": prefix_line_matches,
        } if verify_git_history else None,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-git-history", action="store_true",
                        help="verify evidence/head/fix commits and original source hashes in available Git history")
    parser.add_argument("--fail-on-provenance-gap", action="store_true",
                        help="return nonzero if a source hash is absent from available ancestry")
    args = parser.parse_args()
    try:
        result = reconcile(args.verify_git_history)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(json.dumps({"overall": "FAIL", "errors": [str(exc)]}, indent=2))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["overall"] == "FAIL":
        return 1
    if args.fail_on_provenance_gap and result["source_hash_reconciliation"] and result["source_hash_reconciliation"]["not_found_in_available_ancestry"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
