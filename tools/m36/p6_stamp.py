#!/usr/bin/env python3
"""M36 / P6 - record a batch's evidence commit and a verified recovery bundle in the ledger.

The batch adjudication runs before its own audit commit exists, so the SHA that contains the
evidence cannot be written by ``p6_apply.py``.  This tool closes that gap with real, verified
SHAs only:

    python tools/m36/p6_stamp.py p6-batch-003 <evidence-commit-sha> \
        [--bundle /home/user/recovery/drillmaster-xxxxxxx.bundle <sha256> [<captured-head>]]

Every SHA is checked to resolve in this repository and (for the evidence commit) to be an ancestor
of HEAD; nothing is written if a check fails.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/audits/m36-evidence"


def resolve_commit(rev: str) -> str | None:
    result = subprocess.run(["git", "rev-parse", "--verify", f"{rev}^{{commit}}"], cwd=ROOT,
                            capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def is_ancestor(rev: str, of: str = "HEAD") -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", rev, of], cwd=ROOT,
                          capture_output=True).returncode == 0


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    batch, evidence_commit = sys.argv[1], sys.argv[2]
    bundle_args = sys.argv[3:]

    evidence_commit_full = resolve_commit(evidence_commit)
    if not evidence_commit_full:
        print(f"{evidence_commit} does not resolve in this repository - refusing to record it")
        return 2
    if not is_ancestor(evidence_commit_full):
        print(f"{evidence_commit_full} is not an ancestor of HEAD - refusing to record it")
        return 2

    ledger_path = EVIDENCE / "m36-master-ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    entry = next((b for b in ledger.get("batches", []) if b["batch"] == batch), None)
    if entry is None:
        print(f"{batch} is not in the ledger batches")
        return 2
    payload_path = f"docs/audits/m36-evidence/{batch}.json"
    if subprocess.run(["git", "cat-file", "-e", f"{evidence_commit_full}:{payload_path}"],
                      cwd=ROOT, capture_output=True).returncode:
        print(f"{evidence_commit_full} does not contain {payload_path} - refusing to record it")
        return 2
    entry["evidence_commit"] = evidence_commit_full
    latest_payload = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", payload_path], cwd=ROOT,
        capture_output=True, text=True,
    )
    if latest_payload.returncode == 0 and latest_payload.stdout.strip():
        entry["payload_latest_commit"] = latest_payload.stdout.strip()
        entry["payload_latest_commit_subject"] = subprocess.run(
            ["git", "show", "-s", "--format=%s", entry["payload_latest_commit"]],
            cwd=ROOT, capture_output=True, text=True,
        ).stdout.strip()

    if bundle_args:
        if bundle_args[0] != "--bundle" or len(bundle_args) < 3:
            print("bundle usage: --bundle <path> <sha256> [<captured-head>]")
            return 1
        path, digest = bundle_args[1], bundle_args[2]
        captured = bundle_args[3] if len(bundle_args) > 3 else evidence_commit_full
        bundle_path = Path(path)
        if not bundle_path.is_absolute():
            bundle_path = ROOT / bundle_path
        if not bundle_path.is_file():
            print(f"bundle is not available at {path} - refusing to record verification")
            return 2
        actual_digest = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
        if actual_digest.lower() != digest.lower():
            print(f"bundle SHA-256 mismatch for {path}: expected {digest}, got {actual_digest}")
            return 2
        verify = subprocess.run(["git", "bundle", "verify", str(bundle_path)], cwd=ROOT,
                                capture_output=True, text=True)
        if verify.returncode:
            print(f"git bundle verify failed for {path}: {verify.stderr.strip() or verify.stdout.strip()}")
            return 2
        heads = subprocess.run(["git", "bundle", "list-heads", str(bundle_path)], cwd=ROOT,
                               capture_output=True, text=True)
        if heads.returncode:
            print(f"could not read bundle heads for {path}: {heads.stderr.strip()}")
            return 2
        advertised = [line.split()[0] for line in heads.stdout.splitlines() if line.split()]
        candidates = [head for head in advertised if head.startswith(captured)]
        if len(candidates) != 1:
            print(f"captured head {captured} is not one unambiguous advertised bundle head")
            return 2
        bundles = ledger.setdefault("recovery_bundles", [])
        bundles = [b for b in bundles if b.get("file") != path]
        bundles.append({
            "file": path, "sha256": actual_digest, "captured_head": candidates[0],
            "verification": {
                "status": "VERIFIED", "sha256_match": True, "git_bundle_verify": "PASS",
                "advertised_head_match": True,
                "verified_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
        })
        bundles.sort(key=lambda b: b["captured_head"])
        ledger["recovery_bundles"] = bundles

    ledger["generated_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ledger_path.write_text(json.dumps(ledger, indent=1, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print(f"{batch}: evidence_commit {evidence_commit_full} recorded"
          + (f"; bundle {bundle_args[1]} recorded" if bundle_args else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
