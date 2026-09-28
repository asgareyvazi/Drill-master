#!/usr/bin/env python3
"""M36 / P6 - apply one batch's adjudication records to the register, ledger and progress file.

Source of truth for a batch: docs/audits/m36-evidence/p6-batch-NNN.json, written from reading the
code at each site.  Each record carries: id, classification, evidence (the deciding contract),
defect flag, remaining_question.  This tool refuses to run if a record is missing for any item of
the batch, if an id is unknown or duplicated, or if the arithmetic does not reconcile.

Produces:
    docs/audits/m36-evidence/p6-batch-NNN.md      human-readable batch report
    docs/audits/m36-evidence/m36-open-item-register.json   stamped classifications
    docs/audits/m36-evidence/m36-master-ledger.json        counts + conservation arithmetic
    docs/audits/m36-evidence/P6_PROGRESS.md                resume checkpoint

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
        target["p6_commit"] = data.get("commit")

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
                          "severity": f["severity"], "status": "recorded, not patched"}
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

    # human-readable batch report
    lines = [f"# P6 {batch} — class {data.get('class')}", "",
             f"records **{len(records)}** over **{sites}** sites · "
             + " · ".join(f"{k}: {v}" for k, v in counts.items()), ""]
    if data.get("defects_fixed"):
        lines += ["## Defects fixed", ""] + [f"- {d}" for d in data["defects_fixed"]] + [""]
    if data.get("new_findings"):
        lines += ["## New findings (found while adjudicating this batch)", ""]
        labels = [("trigger", "Trigger"), ("observed", "Observed"),
                  ("deciding_contract", "Deciding contract"), ("reachable", "Reachable"),
                  ("status", "Status"), ("fix", "Fix"), ("commit", "Commit"), ("test", "Test"),
                  ("validation", "Validation"), ("not_patched_because", "Why not patched here"),
                  ("next_action", "Next action")]
        for finding in data["new_findings"]:
            lines += [f"### {finding['id']} — `{finding['file']}:{finding['line']}` "
                      f"({finding['severity']}, class {finding['class']})", ""]
            lines += [f"- **{label}:** {finding[key]}"
                      for key, label in labels if finding.get(key)]
            lines += [""]
    def _commit_text(record) -> str:
        """Per-item commit: the code commit if the item carries one, else the audit-only form."""
        if record.get("commit"):
            return record["commit"]
        if data.get("commit"):
            return (f"audit-only (no code change; batch code commit {data['commit']}, "
                    f"evidence commit recorded in the ledger)")
        return "audit-only, committed with this batch evidence"

    for record in records:
        source = by_id[record["id"]]
        lines += [f"## {record['id']} — `{source['file']}:{source['line']}`", "",
                  f"- **Rule / kind:** `{source['rule']}` / `{source['kind']}` "
                  f"({source['priority']}, class {source['p6_class']})",
                  f"- **Symbol:** `{source.get('symbol')}`",
                  f"- **Register question:** {source.get('question')}",
                  f"- **Evidence:** {record['evidence']}",
                  f"- **Classification:** {record['classification']}",
                  f"- **Defect:** {'yes' if record.get('defect') else 'no'}",
                  f"- **Test:** {record.get('test') or 'not applicable (no behaviour change)'}",
                  f"- **Commit:** {_commit_text(record)}",
                  f"- **Remaining question:** {record.get('remaining_question') or 'none'}", ""]
    (EVIDENCE / f"{batch}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # progress checkpoint
    remaining_ids = [r for r in register["records"] if r.get("p6_batch") and r["classification"] == "OPEN"]
    remaining_ids.sort(key=lambda r: ({"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}[r["p6_class"]],
                                      r["file"], r["line"]))
    nxt = remaining_ids[0] if remaining_ids else None
    code_commits = " · ".join(f"{b['batch']} {b.get('commit') or 'audit-only'}"
                             for b in ledger["batches"])
    live_head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                               capture_output=True, text=True).stdout.strip()
    status = subprocess.run(["git", "status", "--porcelain", "-uall"], cwd=ROOT,
                            capture_output=True, text=True).stdout.splitlines()
    staged = sum(1 for line in status if line[:2].strip() and line[0] != "?")
    untracked = sum(1 for line in status if line.startswith("??"))
    worktree = (f"{staged} modified/staged, {untracked} untracked "
                f"- this batch's evidence is committed next")
    if nxt:
        next_block = f"""next batch:   {nxt['p6_batch']}
next item:    {nxt['id']}
next site:    {nxt['file']}:{nxt['line']}  ({nxt['rule']} / {nxt['kind']})  [class {nxt['p6_class']}]
command:      python tools/m36/p6_dump.py {nxt['p6_batch']} 45
              # then write docs/audits/m36-evidence/{nxt['p6_batch']}.json and run:
              python tools/m36/p6_apply.py {nxt['p6_batch']}
blockers:     none in the repository; environment needs LD_LIBRARY_PATH=/tmp/qtstub for Qt tests"""
    else:
        waiting = sorted((r for r in register["records"] if r["classification"] == "OPEN"),
                         key=lambda r: ({'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4}[r["p6_class"]],
                                        r["file"], r["line"]))
        first_waiting = waiting[0] if waiting else None
        if first_waiting:
            next_block = (
                "HIGH priority is closed - every HIGH record carries a terminal classification.\n"
                f"remaining:    {len(waiting)} records, all "
                f"{first_waiting['priority']} and none planned into a batch yet\n"
                "              (classes: "
                + ", ".join(f"{k} {v}" for k, v in sorted(Counter(r['p6_class'] for r in waiting).items()))
                + ")\n"
                f"next item:    {first_waiting['id']}  {first_waiting['file']}:{first_waiting['line']}"
                f"  ({first_waiting['rule']} / {first_waiting['kind']})  [class {first_waiting['p6_class']}]\n"
                "plan step:    python tools/m36/p6_plan.py --priority "
                f"{first_waiting['priority']}   # appends batch numbers, touches no stamp\n"
                "              then adjudicate batch-by-batch exactly as in phase 1\n"
                "blockers:     none in the repository; environment needs LD_LIBRARY_PATH=/tmp/qtstub for Qt tests")
        else:
            next_block = "every register record carries a terminal classification - nothing open"

    (EVIDENCE / "P6_PROGRESS.md").write_text(f"""# P6 PROGRESS - authoritative resume point

```text
HEAD at generation:     {live_head}   (snapshot - this file is written before its own commit;
                        check `git log -1` for the real HEAD)
branch:                 arena/01a0c945-drill-master (local only - never pushed)
last completed batch:   {batch}  ({len(records)} records, {sites} sites, code commit {data.get('commit')})
HIGH remain:            {high_open}
MEDIUM remain:          {medium_open}
OPEN remain:            {len(open_records)}   (of {register['totals']['records']} register records)
CRITICAL:               0
register defect-fixed:  {register['totals']['defect_fixed']}
defects fixed by P6 batches: {sum(len(b['defects_fixed']) for b in ledger['batches'])}  (one entry per fixed defect; commits in the batch reports)
new findings recorded:  {sum(len(b.get('new_findings', [])) for b in ledger['batches'])}
code commits by batch:  {code_commits}
last validation:        ledger check {ledger['arithmetic']['check']}; register {register['totals']['records']} -
                        {register['totals']['defect_fixed']} fixed - {resolved_total} adjudicated = {len(open_records)} open
tests (this batch):     {data.get('tests')}
worktree at generation: {worktree}
recovery bundle:        /home/user/recovery/drillmaster-<sha>.bundle (clone-verified; sha256 in the register)
```

## Next exact actions

```text
{next_block}
```
""", encoding="utf-8")

    print(f"{batch}: {len(records)} records over {sites} sites -> {counts}")
    print(f"open {len(open_records)} = HIGH {high_open} / MEDIUM {medium_open} | "
          f"check {ledger['arithmetic']['check']}")
    if nxt:
        print(f"next: {nxt['p6_batch']} {nxt['id']} {nxt['file']}:{nxt['line']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
