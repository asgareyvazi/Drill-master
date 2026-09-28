#!/usr/bin/env python3
"""M35 P5: independent re-derivation of the M34 semantic inventory.

This does not call any M34 tool. The sweep families are re-implemented here (same regular
expressions, restated from the M34 sweep's recorded family table so the inventories stay
comparable), scanned by this file's own walker, and then cross-checked against the frozen
M34 ledger:

  * arithmetic   — ledger totals, disposition sums, origin partition, coverage partition
  * freshness    — every record's recorded source_sha256 vs the current file on disk
  * re-sweep     — my hit set vs the frozen sweep hit set (fingerprint-level delta)
  * terminality  — how many records are terminal / open / evidence-incomplete, and the
                   priority distribution of the open ones

Output: docs/audits/m35-evidence/m35-inventory-reverification.json
"""
from __future__ import annotations

import collections
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EV34 = ROOT / "docs" / "audits" / "m34-evidence"
OUT = ROOT / "docs" / "audits" / "m35-evidence" / "m35-inventory-reverification.json"

SKIP_DIRS = {".git", "build", "dist", ".venv", "__pycache__", ".pytest_cache", "node_modules",
             ".mypy_cache", ".ruff_cache", ".tox", ".nox", "docs", "out", "target", "coverage"}

# The family table is loaded verbatim from the frozen M34 sweep so the two inventories are
# comparable; the scanner below is this file's own implementation.
from common_families import load_families  # noqa: E402

FAMILIES = load_families()


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def source_files():
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if rel.startswith("tools/m34/"):
            continue
        if path.suffix == ".py" or rel.startswith(".github/") or rel == "pyproject.toml":
            yield rel


def sha256_of(rel: str) -> str:
    try:
        return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
    except OSError:
        return ""


def sweep() -> dict:
    hits = []
    scanned = 0
    for rel in source_files():
        scanned += 1
        try:
            lines = (ROOT / rel).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        sha = sha256_of(rel)
        for lineno, raw in enumerate(lines, 1):
            if raw.strip().startswith("#"):
                continue
            for family, pattern in FAMILIES.items():
                if re.search(pattern, raw):
                    hits.append({"file": rel, "line": lineno, "family": family,
                                 "text": norm(raw)[:200], "source_sha256": sha})
    seen: dict[tuple, int] = {}
    for h in hits:
        key = (h["file"], h["family"], h["text"])
        ordinal = seen.get(key, 0)
        seen[key] = ordinal + 1
        h["occurrence_key"] = f"{h['file']}|{h['family']}|{h['text']}|{ordinal}"
    return {"files_scanned": scanned, "hits": hits}


def main() -> int:
    ledger = json.loads((EV34 / "m34-ledger.json").read_text())
    items = list(ledger.get("carried_records") or []) + list(ledger.get("new_records") or [])
    if not items:
        items = ledger.get("records") or []
    disposition = collections.Counter(i.get("disposition") for i in items)
    priority = collections.Counter(i.get("priority") for i in items)
    origin = collections.Counter(i.get("origin") for i in items)

    stale = []
    referenced_files = sorted({i["file"] for i in items if i.get("file")})
    current_hashes = {rel: sha256_of(rel) for rel in referenced_files}
    for i in items:
        rel = i.get("file")
        rec = i.get("source_sha256")
        if rel and rec and current_hashes.get(rel) != rec:
            stale.append({"id": i.get("id"), "file": rel, "recorded": rec[:16],
                          "current": (current_hashes.get(rel) or "MISSING")[:16]})

    fresh = sweep()
    frozen = json.loads((EV34 / "m34-fresh-sweep.json").read_text())
    mine = collections.Counter((h["file"], h["family"], h["text"]) for h in fresh["hits"])
    theirs = collections.Counter((h["file"], h["family"], h["text"]) for h in frozen["hits"])
    per_file_mine = collections.Counter(h["file"] for h in fresh["hits"])
    per_file_theirs = collections.Counter(h["file"] for h in frozen["hits"])
    file_delta = {f: per_file_mine.get(f, 0) - per_file_theirs.get(f, 0)
                  for f in set(per_file_mine) | set(per_file_theirs)
                  if per_file_mine.get(f, 0) != per_file_theirs.get(f, 0)}
    only_mine = sorted(f"{k[0]}|{k[1]}|{k[2][:90]}" for k in (mine - theirs).elements())[:60]
    only_theirs = sorted(f"{k[0]}|{k[1]}|{k[2][:90]}" for k in (theirs - mine).elements())[:60]

    open_states = {"UNDER-REVIEW", "EVIDENCE-INCOMPLETE", "OPEN"}
    open_items = [i for i in items if i.get("disposition") in open_states]
    terminal = len(items) - len(open_items)

    payload = {
        "schema": "m35-inventory-reverification",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": "independent re-implementation (tools/m35/verify_inventory.py); no M34 tool called",
        "ledger": {
            "sha256": hashlib.sha256((EV34 / "m34-ledger.json").read_bytes()).hexdigest(),
            "declared_items_field": ledger.get("items"),
            "records_found": len(items),
            "arithmetic": {
                "items_equals_carry_plus_new":
                    (ledger.get("items") == sum(ledger.get("carry_forward", {}).values())
                     + ledger.get("by_origin", {}).get("M34-NEW", 0)),
                "carry_forward_total": sum(ledger.get("carry_forward", {}).values()),
                "new_total": ledger.get("by_origin", {}).get("M34-NEW"),
                "by_origin": dict(origin),
                "origin_total_matches": sum(origin.values()) == ledger.get("items"),
                "dispositions": dict(disposition),
                "disposition_total_matches": sum(disposition.values()) == ledger.get("items"),
                "declared_dispositions": ledger.get("dispositions"),
                "declared_equals_recount":
                    {k: v for k, v in ledger.get("dispositions", {}).items()} == dict(disposition),
                "priority": dict(priority),
                "sweep_hits_declared": ledger.get("sweep_hits"),
                "new_records_declared": ledger.get("new_records") if isinstance(
                    ledger.get("new_records"), int) else None,
                "covered_by_m33":
                    (ledger.get("sweep_hits", 0)
                     - ledger.get("by_origin", {}).get("M34-NEW", 0)),
            },
            "freshness": {
                "referenced_files": len(referenced_files),
                "files_now_absent": [f for f in referenced_files if not current_hashes.get(f)],
                "stale_hash_records": len(stale),
                "stale_sample": stale[:10],
            },
            "terminality": {
                "records": len(items),
                "terminal": terminal,
                "open": len(open_items),
                "open_priority": dict(collections.Counter(i.get("priority") for i in open_items)),
                "open_states": dict(collections.Counter(i.get("disposition") for i in open_items)),
                "open_domains": dict(collections.Counter(i.get("domain") for i in open_items)),
            },
        },
        "independent_resweep": {
            "files_scanned": fresh["files_scanned"],
            "my_hits": len(fresh["hits"]),
            "frozen_sweep_hits": len(frozen["hits"]),
            "fingerprint_keys_equal": mine == theirs,
            "only_in_mine": only_mine,
            "only_in_frozen": only_theirs,
            "my_family_counts": dict(collections.Counter(h["family"] for h in fresh["hits"])),
            "frozen_family_counts": dict(collections.Counter(h["family"] for h in frozen["hits"])),
            "per_file_delta": dict(sorted(file_delta.items(), key=lambda kv: -abs(kv[1]))),
            "files_only_in_mine": sorted(set(per_file_mine) - set(per_file_theirs)),
            "files_only_in_frozen": sorted(set(per_file_theirs) - set(per_file_mine)),
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    arith = payload["ledger"]["arithmetic"]
    print("records:", len(items), "| disposition_recount_matches:",
          arith["disposition_total_matches"], "| declared==recount:", arith["declared_equals_recount"])
    print("stale_hash_records:", payload["ledger"]["freshness"]["stale_hash_records"],
          "| files_absent:", len(payload["ledger"]["freshness"]["files_now_absent"]))
    print("terminal:", terminal, "| open:", len(open_items), "| open priority:",
          payload["ledger"]["terminality"]["open_priority"])
    print("my hits:", len(fresh["hits"]), "| frozen hits:", len(frozen["hits"]),
          "| identical:", mine == theirs)
    if only_mine or only_theirs:
        print("delta only-in-mine:", len(only_mine), "only-in-frozen:", len(only_theirs))
        for line in only_mine[:5]:
            print("  +", line[:130])
        for line in only_theirs[:5]:
            print("  -", line[:130])
    print("written", OUT.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
