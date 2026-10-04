#!/usr/bin/env python3
"""M36 / P6 - apply one batch's adjudication records to the register and ledger.

Source of truth for a batch: docs/audits/m36-evidence/p6-batch-NNN.json. This tool checks the
batch against the assigned register records, stamps classifications/evidence, and updates the
machine-readable conservation ledger. The accounting keeps three quantities separate:

    total register records = pre-P6 DEFECT-FIXED records + P6-batch adjudications + current OPEN

``start_open`` means records that were actually open when P6 began; it excludes records already
classified DEFECT-FIXED before P6. Secondary NEW-P6 findings are recorded separately and are never
added to the original-register arithmetic.

P6_PROGRESS.md is a human-maintained status snapshot and is deliberately not generated here.

usage: python tools/m36/p6_apply.py p6-batch-002
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/audits/m36-evidence"
VALID = {"VERIFIED-CORRECT", "INTENTIONAL", "DUPLICATE/FALSE-POSITIVE", "GENUINE_DEFECT",
         "DOMAIN_DECISION_REQUIRED", "INSUFFICIENT_EVIDENCE"}
TERMINAL = VALID  # every evidence-backed classification is terminal for the register


def calculate_accounting(register: dict, batches: list[dict]) -> dict:
    """Return independently derived P6 conservation arithmetic plus validation errors."""
    records = register.get("records", [])
    ids = [r.get("id") for r in records]
    errors: list[str] = []
    if len(ids) != len(set(ids)):
        errors.append("register record IDs are not unique")

    total = len(records)
    if register.get("totals", {}).get("records") != total:
        errors.append("register totals.records does not match records array")

    pre_p6_fixed = [r for r in records
                    if r.get("classification") == "DEFECT-FIXED" and not r.get("p6_batch")]
    if any(r.get("classification") == "DEFECT-FIXED" and r.get("p6_batch") for r in records):
        errors.append("a batch-assigned record is labeled pre-P6 DEFECT-FIXED")

    open_records = [r for r in records if r.get("classification") == "OPEN"]
    if register.get("totals", {}).get("open") != len(open_records):
        errors.append("register totals.open does not match OPEN records")
    if register.get("totals", {}).get("open_by_priority", {}) != dict(
            Counter(r.get("priority", "UNKNOWN") for r in open_records).most_common()):
        errors.append("register open_by_priority does not match OPEN records")
    if register.get("totals", {}).get("open_by_class", {}) != dict(
            Counter(r.get("p6_class", "UNKNOWN") for r in open_records).most_common()):
        errors.append("register open_by_class does not match OPEN records")

    adjudicated = [r for r in records
                   if r.get("p6_batch") and r.get("classification") in TERMINAL]
    unbatched_terminal = [r for r in records
                          if not r.get("p6_batch")
                          and r.get("classification") not in {"OPEN", "DEFECT-FIXED"}]
    if unbatched_terminal:
        errors.append("terminal records outside the P6 batches or pre-P6 fixed set: "
                      + ", ".join(r.get("id", "<no id>") for r in unbatched_terminal))

    by_batch = Counter(r["p6_batch"] for r in adjudicated)
    records_by_batch: dict[str, list[dict]] = {}
    for record in adjudicated:
        records_by_batch.setdefault(record["p6_batch"], []).append(record)
    declared_by_batch: Counter = Counter()
    seen_batches: set[str] = set()
    for batch in batches:
        name = batch.get("batch")
        if name in seen_batches:
            errors.append(f"duplicate ledger batch {name}")
        seen_batches.add(name)
        declared_by_batch[name] += batch.get("records", 0)
        batch_records = records_by_batch.get(name, [])
        if dict(Counter(r.get("classification") for r in batch_records)) != batch.get("by_classification", {}):
            errors.append(f"ledger class counts do not match register assignments for {name}")
        sites = len({(r.get("file"), r.get("line")) for r in batch_records})
        if sites != batch.get("sites"):
            errors.append(f"ledger site count does not match register assignments for {name}")
    if dict(by_batch) != dict(declared_by_batch):
        errors.append("ledger batch record counts do not match terminal register assignments")

    register_fixed_total = sum(r.get("classification") == "DEFECT-FIXED" for r in records)
    if register.get("totals", {}).get("defect_fixed") != register_fixed_total:
        errors.append("register totals.defect_fixed does not match DEFECT-FIXED records")
    if register_fixed_total != len(pre_p6_fixed):
        errors.append("DEFECT-FIXED records are not all pre-P6 and unbatched")

    start_open = total - len(pre_p6_fixed)
    start_by_priority = dict(Counter(
        r.get("priority", "UNKNOWN") for r in records if r not in pre_p6_fixed
    ).most_common())
    current_open = len(open_records)
    conservation = total == len(pre_p6_fixed) + len(adjudicated) + current_open
    progress = start_open == len(adjudicated) + current_open
    if not conservation:
        errors.append("total != pre-P6 fixed + batch-adjudicated + current OPEN")
    if not progress:
        errors.append("P6-start OPEN != batch-adjudicated + current OPEN")

    return {
        "register_records_at_p6_start": total,
        "pre_p6_defect_fixed_records": len(pre_p6_fixed),
        "open_records_at_p6_start": start_open,
        "open_by_priority_at_p6_start": start_by_priority,
        "adjudicated_by_p6_batches": len(adjudicated),
        "current_open": current_open,
        "batch_record_counts": dict(sorted(by_batch.items())),
        "check": not errors,
        "errors": errors,
        "formula": "register_records_at_p6_start = pre_p6_defect_fixed_records + adjudicated_by_p6_batches + current_open",
        "note": ("The two pre-P6 DEFECT-FIXED records are not batch adjudications. Batch classifications "
                 "including DOMAIN_DECISION_REQUIRED are terminal register dispositions; secondary "
                 "NEW-P6 findings and owner decisions are a separate namespace."),
    }


def _fix_commit_for_record(batch_data: dict, record_id: str) -> str | None:
    """Read a directly linked fix commit from existing batch-level fix metadata."""
    for fix in batch_data.get("defects_fixed", []):
        if not isinstance(fix, dict):
            continue
        covered = fix.get("records") or []
        if fix.get("id") == record_id or record_id in covered:
            return fix.get("fix_commit") or fix.get("commit")
    return None


def main() -> int:
    batch = sys.argv[1] if len(sys.argv) > 1 else "p6-batch-002"
    adjudication_path = EVIDENCE / f"{batch}.json"
    if not adjudication_path.is_file():
        print(f"missing adjudication file: {adjudication_path}")
        return 1
    data = json.loads(adjudication_path.read_text(encoding="utf-8"))
    records = data["items"]

    ids = [r["id"] for r in records]
    if len(ids) != len(set(ids)):
        duplicates = [i for i, n in Counter(ids).items() if n > 1]
        print("duplicate ids in the batch:", duplicates)
        return 1

    register_path = EVIDENCE / "m36-open-item-register.json"
    register = json.loads(register_path.read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in register["records"]}

    expected = [r["id"] for r in register["records"] if r.get("p6_batch") == batch]
    missing = [i for i in expected if i not in set(ids)]
    unknown = [i for i in ids if i not in by_id]
    wrong_batch = [i for i in ids if i in by_id and by_id[i].get("p6_batch") != batch]
    if missing or unknown or wrong_batch:
        print("batch assignment mismatch — missing:", missing,
              "unknown:", unknown, "assigned elsewhere:", wrong_batch)
        return 1

    bad = [r["id"] for r in records if r["classification"] not in VALID]
    if bad:
        print("invalid classifications:", bad)
        return 1
    for record in records:
        if not (record.get("evidence") or "").strip():
            print("record without evidence:", record["id"])
            return 1

    ledger_path = EVIDENCE / "m36-master-ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.is_file() else {
        "schema": "m36-master-ledger", "batches": [],
    }
    old_summary = next((b for b in ledger["batches"] if b.get("batch") == batch), {})

    # Stamp in memory. A specifically cited or batch-level code commit takes precedence; if the
    # payload does not carry one, retain a verified existing per-record stamp rather than erase it.
    for record in records:
        target = by_id[record["id"]]
        target["classification"] = record["classification"]
        target["p6_evidence"] = record["evidence"]
        target["p6_remaining_question"] = record.get("remaining_question")
        target["p6_defect"] = bool(record.get("defect"))
        target["p6_commit"] = (record.get("commit") or data.get("commit")
                               or _fix_commit_for_record(data, record["id"])
                               or target.get("p6_commit"))

    open_records = [r for r in register["records"] if r["classification"] == "OPEN"]
    register["totals"]["records"] = len(register["records"])
    register["totals"]["open"] = len(open_records)
    register["totals"]["open_by_priority"] = dict(
        Counter(r["priority"] for r in open_records).most_common())
    register["totals"]["open_by_class"] = dict(
        Counter(r.get("p6_class", "UNKNOWN") for r in open_records).most_common())
    register["totals"]["defect_fixed"] = sum(
        r["classification"] == "DEFECT-FIXED" for r in register["records"])
    register["generated_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    counts = dict(Counter(r["classification"] for r in records).most_common())
    sites = len({(r["file"], r["line"]) for r in records})
    ledger["batches"] = [b for b in ledger["batches"] if b.get("batch") != batch]
    ledger["batches"].append({
        "batch": batch, "class": data.get("class"), "records": len(records), "sites": sites,
        "by_classification": counts, "defects_fixed": data.get("defects_fixed", []),
        "new_findings": [{"id": f["id"], "file": f["file"], "line": f["line"],
                          "severity": f["severity"],
                          "status": f.get("status", "recorded, not patched"),
                          "commit": f.get("commit"), "test": f.get("test")}
                         for f in data.get("new_findings", [])],
        "evidence_commit": data.get("evidence_commit") or old_summary.get("evidence_commit"),
        "commit": data.get("commit"), "tests": data.get("tests"),
        "head": data.get("head"),
        "head_commit": old_summary.get("head_commit"),
        "source_tree": old_summary.get("source_tree"),
        "head_provenance": old_summary.get("head_provenance"),
        "staleness": data.get("staleness"),
        "payload_latest_commit": old_summary.get("payload_latest_commit"),
        "payload_latest_commit_subject": old_summary.get("payload_latest_commit_subject"),
        "supplemental_test_evidence_commits": old_summary.get("supplemental_test_evidence_commits", []),
        "production_commits": old_summary.get("production_commits", []),
    })
    ledger["batches"].sort(key=lambda b: b["batch"])

    accounting = calculate_accounting(register, ledger["batches"])
    if not accounting["check"]:
        print("accounting validation failed:", accounting["errors"])
        return 1

    ledger["register_records_at_p6_start"] = accounting["register_records_at_p6_start"]
    ledger["start_open"] = accounting["open_records_at_p6_start"]
    ledger["start_by_priority"] = accounting["open_by_priority_at_p6_start"]
    ledger["start_high"] = accounting["open_by_priority_at_p6_start"].get("HIGH", 0)
    ledger["start_medium"] = accounting["open_by_priority_at_p6_start"].get("MEDIUM", 0)
    ledger["arithmetic"] = accounting
    ledger["open_by_priority"] = register["totals"]["open_by_priority"]
    ledger["open_by_class"] = register["totals"]["open_by_class"]
    ledger["generated_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    register_path.write_text(json.dumps(register, indent=1, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    ledger_path.write_text(json.dumps(ledger, indent=1, ensure_ascii=False) + "\n",
                           encoding="utf-8")

    high_open = sum(1 for r in open_records if r["priority"] == "HIGH")
    medium_open = sum(1 for r in open_records if r["priority"] == "MEDIUM")
    print(f"{batch}: {len(records)} records over {sites} sites -> {counts}")
    print(f"register {accounting['register_records_at_p6_start']} total = "
          f"{accounting['pre_p6_defect_fixed_records']} pre-P6 fixed + "
          f"{accounting['adjudicated_by_p6_batches']} batch-adjudicated + "
          f"{accounting['current_open']} current open | check {accounting['check']}")
    print(f"current open by priority: HIGH {high_open} / MEDIUM {medium_open}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
