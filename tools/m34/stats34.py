#!/usr/bin/env python3
"""M34 inventory reconciliation: M30/M31/M32/M33/M34 compared, deltas classified, per-family table."""
from __future__ import annotations
import json, hashlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / "docs" / "audits" / "m34-evidence"
ledger = json.loads((EV / "m34-ledger.json").read_text())
KIND2FAM = json.loads((Path(__file__).parent / "kind_family_map.json").read_text())
for _r in ledger["carried_records"] + ledger["new_records"]:
    _r["family"] = KIND2FAM.get(_r.get("kind"), _r.get("kind"))
records = ledger["carried_records"] + ledger["new_records"]
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")

fam = defaultdict(Counter)
for r in records:
    fam[r["family"]][r["disposition"]] += 1
family_table = []
for name, c in sorted(fam.items(), key=lambda kv: -sum(kv[1].values())):
    family_table.append({"family": name, "total": sum(c.values()),
                         "verified_correct": c.get("VERIFIED-CORRECT", 0),
                         "intentional": c.get("INTENTIONAL-BY-DESIGN", 0),
                         "under_review": c.get("UNDER-REVIEW", 0),
                         "defect_fixed": c.get("DEFECT-FIXED", 0),
                         "evidence_incomplete": c.get("EVIDENCE-INCOMPLETE", 0),
                         "removed_with_evidence": c.get("REMOVED-WITH-EVIDENCE", 0),
                         "external_acceptance_only": c.get("EXTERNAL-ACCEPTANCE-ONLY", 0)})

open_by_rule = defaultdict(Counter)
for r in records:
    if r["disposition"] in ("UNDER-REVIEW", "EVIDENCE-INCOMPLETE"):
        open_by_rule[r["rule"]][r["priority"]] += 1
open_table = [{"rule": k, "total": sum(v.values()), "priorities": dict(v)}
              for k, v in sorted(open_by_rule.items(), key=lambda kv: -sum(kv[1].values()))]

ei = [{"path": r["file"], "line": r.get("line_m34") or r.get("line_m33"), "family": r["family"],
       "rule": r["rule"], "evidence": r["evidence"][:220]} for r in records
      if r["disposition"] == "EVIDENCE-INCOMPLETE"]
nolines = [{"path": r["file"], "line_m34": r.get("line_m34"), "line_m33": r.get("line_m33"),
            "origin": r.get("origin"), "disposition": r["disposition"], "evidence": r["evidence"][:200]}
           for r in records if r.get("origin") == "M33-NO-LINE" or r.get("carry_forward") == "M33-NO-LINE"]
fixed = [{"path": r["file"], "line": r.get("line_m34"), "family": r["family"], "rule": r["rule"],
          "evidence": r["evidence"][:200]} for r in records if r["disposition"] == "DEFECT-FIXED"]
external = [{"path": r["file"], "family": r["family"], "rule": r["rule"], "evidence": r["evidence"][:180]}
            for r in records if r["disposition"] == "EXTERNAL-ACCEPTANCE-ONLY"]
removed = [{"path": r["file"], "line": r.get("line_m34"), "rule": r["rule"], "evidence": r["evidence"][:180]}
           for r in records if r["disposition"] == "REMOVED-WITH-EVIDENCE"]

payload = {
    "schema": "m34-reconciliation",
    "generated_utc": NOW,
    "ledger": {"path": "docs/audits/m34-evidence/m34-ledger.json",
               "sha256": hashlib.sha256((EV / "m34-ledger.json").read_bytes()).hexdigest(),
               "items": len(records)},
    "inventories": {
        "M30": {"claimed": 2232, "state": "prior claim — not a target; M34 does not use it as a baseline"},
        "M31": {"claimed": 6860, "state": "prior claim — not a target"},
        "M32": {"claimed_remaining": 3518, "state": "prior claim — verified family-wise only where the "
                                                  "M33 records carrying it are still byte-identical"},
        "M33": {"claimed": 8934, "state": "recovered from docs/audits/m33-evidence/m33-ledger.json; "
                                         "its per-item records are the carry-forward population"},
        "M34": {"independent": len(records),
                "origin": dict(Counter(r.get("origin") for r in records)),
                "explanation": "M33 records carried forward where the file hash still matches "
                               "(SAME-FILE-HASH), plus every fresh-sweep hit M33 did not hold; sweep "
                               "hits M33 already held are de-duplicated rather than re-counted"},
    },
    "delta_classes": {
        "NEW": ledger.get("new_hits"),
        "CARRIED-FORWARD-SAME-FILE-HASH": ledger.get("carry_forward", {}).get("SAME-FILE-HASH"),
        "CARRIED-FORWARD-WITHOUT-LINE": ledger.get("carry_forward", {}).get("M33-NO-LINE"),
        "DUPLICATE-OF-M33-RECORD": ledger.get("sweep_hits_covered_by_m33"),
        "FIXED": sum(1 for r in records if r["disposition"] == "DEFECT-FIXED"),
        "REMOVED-WITH-EVIDENCE": sum(1 for r in records if r["disposition"] == "REMOVED-WITH-EVIDENCE"),
        "INTENTIONAL": sum(1 for r in records if r["disposition"] == "INTENTIONAL-BY-DESIGN"),
        "EXTERNAL": sum(1 for r in records if r["disposition"] == "EXTERNAL-ACCEPTANCE-ONLY"),
        "OPEN": sum(1 for r in records if r["disposition"] in ("UNDER-REVIEW", "EVIDENCE-INCOMPLETE")),
        "note": "a count that changed is not a deletion: every M33 record is either carried (with its "
                "own evidence retained) or replaced by a re-adjudication that keeps the M33 evidence "
                "under `m33_evidence`",
    },
    "readjudication": ledger.get("readjudication_of_inherited_under_review"),
    "m33_state_transitions": dict(Counter(
        f"{r.get('m33_disposition') or 'M34-NEW'} -> {r['disposition']}"
        for r in records if r.get("origin") != "M34-NEW")),
    "families": family_table,
    "open_by_rule": open_table,
    "evidence_incomplete_items": ei,
    "carried_without_line": nolines,
    "defect_fixed_items": fixed,
    "external_items": external,
    "removed_items": removed,
}
(EV / "m34-reconciliation.json").write_text(json.dumps(payload, indent=1))
print("families:", len(family_table), "open rules:", len(open_table))
print("EI items:", len(ei), "no-line:", len(nolines), "fixed:", len(fixed),
      "external:", len(external), "removed:", len(removed))
print("readjudication:", payload["readjudication"])
for r in open_table[:8]:
    print(f"  {r['total']:5} {r['rule']} {r['priorities']}")
