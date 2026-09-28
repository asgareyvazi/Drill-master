#!/usr/bin/env python3
"""M36 / P6 - build the working register and the batch plan from the M35 register.

Source data (never edited in place):
    docs/audits/m35-evidence/m35-open-item-register.json   (1 224 open records, M35)

Outputs:
    docs/audits/m36-evidence/m36-open-item-register.json   (working register: every source record
                                                            plus p6_class, p6_batch, classification;
                                                            OPEN by default - nothing is closed here)
    docs/audits/m36-evidence/p6-plan.json                  (batches of BATCH_SIZE HIGH records,
                                                            ordered by priority class A..E then
                                                            file/line)

Priority classes (mission order):
    A safety / authorization / mutation      B data integrity / persistence / identity
    C engineering calculations               D workflow state / lifecycle
    E lower-risk semantics

The class is derived from the file and the *enclosing symbol* - never from words inside the
evidence window, which over-matched ("session", "user", "update" appear in most windows).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/audits/m36-evidence"
SOURCE_REGISTER = ROOT / "docs/audits/m35-evidence/m35-open-item-register.json"
BATCH_SIZE = 45

# The two records of the W5 fail-open permission gate, fixed in this repository.
FIXED = {
    "INV34-005842": {"commit": "9f45cc4", "note": "EquipmentWidget.save_all_data now logs, reports and "
                    "returns False before any persistence step (tabs/w5_Equipment_Widget.py:771)"},
    "INV34-008380": {"commit": "9f45cc4", "note": "the `pass` handler body was replaced by the "
                    "fail-closed handler (tabs/w5_Equipment_Widget.py:772)"},
}

SAFETY_FILES = ("core/permissions.py", "core/security", "core/auth", "core/managers.py",
                "tabs/w5_", "tabs/w8_", "tabs/w16_", "core/audit")
MUTATION_SYMBOL = re.compile(
    r"save|delete|remove|update|insert|commit|flush|approve|sign|lock|unlock|permission|role|"
    r"login|password|purge|drop|migrat|restore|import|export", re.I)
INTEGRITY_FILES = ("core/database.py", "core/repositories/", "core/import", "core/export",
                   "core/snapshot", "core/backup", "core/migration", "core/persistence")
INTEGRITY_RULES = ("R-SNAP-SERIAL-DEFAULT", "R-SESSION-OTHER", "R-SEL-UNPROVEN",
                   "R-DEF-VALUE-PATH", "R-SEC-TEMP")
ENGINEERING_FILES = ("core/engineering/", "core/cost", "core/kpi", "core/hydraulics",
                     "core/torque", "core/anti_collision", "core/operational_time",
                     "core/time_utils", "core/import_quality")
ENGINEERING_RULES = ("R-NUM-UNKNOWN", "R-PARAM-ARITH", "R-RED-UNPROVEN", "R-RED-ZERO",
                     "R-SPIN-ZERO", "R-PLAN-OTHER", "R-PLAN-BASELINE")
IDENTITY_FILES = ("core/inventory", "core/equipment", "core/workover", "core/sidetrack",
                  "core/well", "core/bha", "core/bit", "tabs/w2_", "tabs/w3", "tabs/w13_")


def classify(record: dict) -> str:
    rel = record["file"]
    symbol = record.get("symbol") or ""
    if rel.startswith(SAFETY_FILES) or MUTATION_SYMBOL.search(symbol):
        return "A"
    if rel.startswith(INTEGRITY_FILES) or record["rule"] in INTEGRITY_RULES:
        return "B"
    if rel.startswith(ENGINEERING_FILES) or record["rule"] in ENGINEERING_RULES:
        return "C"
    if rel.startswith(IDENTITY_FILES):
        return "D"
    return "E"


ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild-register", action="store_true",
                        help="rebuild the working register and the HIGH plan from the M35 source; "
                             "this RESETS every P6 stamp (classification / evidence / p6_commit), so "
                             "it is only for a fresh P6 rebuild")
    parser.add_argument("--priority", default="",
                        help="plan the OPEN records of this priority (e.g. MEDIUM) into new batches "
                             "without touching any classification; default: every unplanned OPEN "
                             "record")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    return parser.parse_args(argv)


def plan_open_records(register_path: Path, priority: str, batch_size: int) -> int:
    """Phase-2 planning: give every unplanned OPEN record a batch number, change nothing else."""
    register = json.loads(register_path.read_text(encoding="utf-8"))
    selected = [r for r in register["records"] if r["classification"] == "OPEN"
                and (not priority or r["priority"] == priority)]
    unplanned = [r for r in selected if not r.get("p6_batch")]
    unplanned.sort(key=lambda r: (ORDER[r["p6_class"]], r["file"], r["line"]))
    if not unplanned:
        print(f"nothing to plan: {len(selected)} OPEN {priority or ''} records, all already batched")
        return 0
    used = {int(r["p6_batch"].rsplit("-", 1)[1]) for r in register["records"] if r.get("p6_batch")}
    first = (max(used) + 1) if used else 2
    for index, record in enumerate(unplanned):
        record["p6_batch"] = f"p6-batch-{first + index // batch_size:03d}"
    batches = []
    for batch in sorted({r["p6_batch"] for r in unplanned}):
        chunk = [r for r in unplanned if r["p6_batch"] == batch]
        batches.append({
            "batch": batch, "priority": chunk[0]["priority"],
            "class": chunk[0]["p6_class"], "records": len(chunk),
            "first_id": chunk[0]["id"], "last_id": chunk[-1]["id"],
            "first_site": f"{chunk[0]['file']}:{chunk[0]['line']}",
            "files": sorted({r["file"] for r in chunk}),
            "sites": len({(r["file"], r["line"]) for r in chunk}),
        })
    register["generated_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    register["phase2_plan"] = {
        "priority": priority or "all", "batch_size": batch_size,
        "planned": len(unplanned), "batches": len(batches),
        "note": ("batch numbers are appended after the highest existing p6_batch; classifications, "
                 "evidence and commit stamps are untouched by this planner"),
    }
    register_path.write_text(json.dumps(register, indent=1, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    plan_name = f"p6-plan{('-' + priority.lower()) if priority else '-phase2'}.json"
    plan = {"schema": "m36-p6-plan", "phase": "phase-2 (open records)",
            "priority": priority or "all", "batch_size": batch_size,
            "by_class": dict(Counter(r["p6_class"] for r in unplanned).most_common()),
            "batches": batches}
    (EVIDENCE / plan_name).write_text(json.dumps(plan, indent=1, ensure_ascii=False) + "\n",
                                      encoding="utf-8")
    print(f"planned {len(unplanned)} OPEN {priority or ''} records into {len(batches)} batches "
          f"x <= {batch_size} -> {plan_name}")
    for batch in batches[:4]:
        print(f"  {batch['batch']} class {batch['class']} records {batch['records']} "
              f"sites {batch['sites']} first {batch['first_id']} {batch['first_site']}")
    if len(batches) > 4:
        print(f"  ... {len(batches) - 4} more")
    return 0


def main(argv=None) -> int:
    args = _parse_args(argv)
    register_path = EVIDENCE / "m36-open-item-register.json"
    if register_path.is_file() and not args.rebuild_register:
        return plan_open_records(register_path, args.priority.upper(), args.batch_size)
    source = json.loads(SOURCE_REGISTER.read_text(encoding="utf-8"))
    records = source["records"]

    for record in records:
        record["register_classification"] = record.get("classification")
        fixed = FIXED.get(record["id"])
        record["classification"] = "DEFECT-FIXED" if fixed else "OPEN"
        record["p6_evidence"] = fixed["note"] if fixed else None
        record["fixed_commit"] = fixed["commit"] if fixed else None
        record["p6_class"] = classify(record)

    open_records = [r for r in records if r["classification"] == "OPEN"]
    high = [r for r in open_records if r["priority"] == "HIGH"]
    order = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}
    high.sort(key=lambda r: (order[r["p6_class"]], r["file"], r["line"]))

    for index, record in enumerate(high):
        record["p6_batch"] = f"p6-batch-{index // BATCH_SIZE + 2:03d}"

    batches = []
    for number in range(0, len(high), BATCH_SIZE):
        chunk = high[number:number + BATCH_SIZE]
        batches.append({
            "batch": chunk[0]["p6_batch"],
            "class": chunk[0]["p6_class"],
            "records": len(chunk),
            "first_id": chunk[0]["id"], "last_id": chunk[-1]["id"],
            "first_site": f"{chunk[0]['file']}:{chunk[0]['line']}",
            "files": sorted({r["file"] for r in chunk}),
            "sites": len({(r["file"], r["line"]) for r in chunk}),
        })

    register = {
        "schema": "m36-open-item-register",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_register": "docs/audits/m35-evidence/m35-open-item-register.json",
        "source_sha256_declared": source.get("source_ledger_sha256"),
        "totals": {
            "records": len(records),
            "open": len(open_records),
            "open_by_priority": dict(Counter(r["priority"] for r in open_records).most_common()),
            "open_by_class": dict(Counter(r["p6_class"] for r in open_records).most_common()),
            "defect_fixed": len([r for r in records if r["classification"] == "DEFECT-FIXED"]),
        },
        "method": ("derived from the M35 register; classification is OPEN unless the record's site "
                   "was fixed and committed in this repository; p6_class orders the mission's "
                   "priority A..E"),
        "records": records,
    }
    (EVIDENCE / "m36-open-item-register.json").write_text(
        json.dumps(register, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    plan = {
        "schema": "m36-p6-plan",
        "batch_size": BATCH_SIZE,
        "high_open": len(high),
        "by_class": dict(Counter(r["p6_class"] for r in high).most_common()),
        "batches": batches,
    }
    (EVIDENCE / "p6-plan.json").write_text(json.dumps(plan, indent=1, ensure_ascii=False) + "\n",
                                           encoding="utf-8")

    print(f"register: {len(records)} records | open {len(open_records)} "
          f"({register['totals']['open_by_priority']}) | defect-fixed {register['totals']['defect_fixed']}")
    print(f"HIGH open: {len(high)} | classes: {plan['by_class']} | batches: {len(batches)} "
          f"x {BATCH_SIZE}")
    for batch in batches[:5]:
        print(f"  {batch['batch']} class {batch['class']} records {batch['records']} "
              f"sites {batch['sites']} first {batch['first_id']} {batch['first_site']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
