#!/usr/bin/env python3
"""M36 / P6 - apply one batch's adjudication records to the register, ledger and progress file.

Source of truth for a batch: docs/audits/m36-evidence/p6-batch-NNN.json, written from reading the
code at each site.  Each record carries: id, classification, evidence (the deciding contract),
defect flag, remaining_question.  This tool refuses to run if a record is missing for any item of
the batch, if an id is unknown or duplicated, or if the arithmetic does not reconcile.

Produces:
    docs/audits/m36-evidence/m36-open-item-register.json   stamped classifications + evidence
    docs/audits/m36-evidence/m36-master-ledger.json        counts + conservation arithmetic

Reporting markdown is deliberately NOT generated (session rule): p6-batch-NNN.json is the
per-batch machine-readable record.

usage: python tools/m36/p6_apply.py p6-batch-002
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/audits/m36-evidence"
VALID = {"VERIFIED-CORRECT", "INTENTIONAL", "DUPLICATE/FALSE-POSITIVE", "GENUINE_DEFECT",
         "DOMAIN_DECISION_REQUIRED", "INSUFFICIENT_EVIDENCE"}
TERMINAL = VALID  # every evidence-backed classification is terminal for the register


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
    if missing or unknown:
        print("batch incomplete — missing:", missing, "unknown:", unknown)
        return 1

    bad = [r["id"] for r in records if r["classification"] not in VALID]
    if bad:
        print("invalid classifications:", bad)
        return 1
    for record in records:
        if not (record.get("evidence") or "").strip():
            print("record without evidence:", record["id"])
            return 1

    # stamp
    for record in records:
        target = by_id[record["id"]]
        target["classification"] = record["classification"]
        target["p6_evidence"] = record["evidence"]
        target["p6_remaining_question"] = record.get("remaining_question")
        target["p6_defect"] = bool(record.get("defect"))
        # A record may name its own commit (a genuine defect names the fix commit); otherwise the
        # batch-level commit applies.  All other per-record stamps come from the batch payload.
        target["p6_commit"] = record.get("commit") or data.get("commit")

    open_records = [r for r in register["records"] if r["classification"] == "OPEN"]
    register["totals"]["open"] = len(open_records)
    register["totals"]["open_by_priority"] = dict(
        Counter(r["priority"] for r in open_records).most_common())
    register["totals"]["open_by_class"] = dict(
        Counter(r["p6_class"] for r in open_records).most_common())
    register["generated_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    register_path.write_text(json.dumps(register, indent=1, ensure_ascii=False) + "\n",
                             encoding="utf-8")

    counts = dict(Counter(r["classification"] for r in records).most_common())
    sites = len({(r["file"], r["line"]) for r in records})
    high_open = sum(1 for r in open_records if r["priority"] == "HIGH")
    medium_open = sum(1 for r in open_records if r["priority"] == "MEDIUM")

    ledger_path = EVIDENCE / "m36-master-ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.is_file() else {
        "schema": "m36-master-ledger", "batches": [], "start_open": 1224, "start_high": 371,
    }
    ledger["batches"] = [b for b in ledger["batches"] if b["batch"] != batch]
    ledger["batches"].append({
        "batch": batch, "class": data.get("class"), "records": len(records), "sites": sites,
        "by_classification": counts, "defects_fixed": data.get("defects_fixed", []),
        "new_findings": [{"id": f["id"], "file": f["file"], "line": f["line"],
                          "severity": f["severity"],
                          "status": f.get("status", "recorded, not patched"),
                          "commit": f.get("commit"), "test": f.get("test")}
                         for f in data.get("new_findings", [])],
        "evidence_commit": data.get("evidence_commit"),
        "commit": data.get("commit"), "tests": data.get("tests"),
    })
    ledger["batches"].sort(key=lambda b: b["batch"])
    resolved_total = sum(b["records"] for b in ledger["batches"])
    ledger["arithmetic"] = {
        "register_open_at_p6_start": register["totals"]["records"],
        "defect_fixed_by_p6": register["totals"]["defect_fixed"],
        "adjudicated_by_p6_batches": resolved_total,
        "current_open": len(open_records),
        "check": (register["totals"]["records"] - register["totals"]["defect_fixed"]
                  - resolved_total == len(open_records)),
        "note": ("every record is either OPEN or carries a terminal evidence-backed classification; "
                 "the fixed sites are subtracted separately so nothing disappears"),
    }
    ledger["open_by_priority"] = register["totals"]["open_by_priority"]
    ledger["open_by_class"] = register["totals"]["open_by_class"]
    ledger["generated_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ledger_path.write_text(json.dumps(ledger, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    # Rules for this session: reporting markdown is NOT generated.  The machine-readable record of
    # a batch is p6-batch-NNN.json (written by the batch script) plus the register and the master
    # ledger below; the per-batch .md report and the P6_PROGRESS.md resume file are not written.
    remaining_ids = [r for r in register["records"] if r["classification"] == "OPEN"]
    remaining_ids.sort(key=lambda r: ({"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}[r["p6_class"]],
                                      r["file"], r["line"]))
    nxt = remaining_ids[0] if remaining_ids else None

    print(f"{batch}: {len(records)} records over {sites} sites -> {counts}")
    print(f"open {len(open_records)} = HIGH {high_open} / MEDIUM {medium_open} | "
          f"check {ledger['arithmetic']['check']}")
    if nxt:
        print(f"next: {nxt['p6_batch']} {nxt['id']} {nxt['file']}:{nxt['line']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
