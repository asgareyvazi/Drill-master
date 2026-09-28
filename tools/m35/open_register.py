#!/usr/bin/env python3
"""M35 P6: the open-item register, plus contract-based adjudication where the repository decides.

Rules of engagement (from the mission):
  * no pattern / naming / "looks intentional" adjudication;
  * evidence must be a contract: an explicit statement in the source (docstring, comment on the
    handler), a test oracle, or a documented API/behavioural contract;
  * anything else stays OPEN and is quantified.

Every open record gets: file, symbol, line, question, missing fact, why it matters, where the
evidence would live, classification and confidence — individually, not by cluster.

Output: docs/audits/m35-evidence/m35-open-item-register.json
        docs/audits/m35-evidence/m35-contract-adjudications.json
"""
from __future__ import annotations

import collections
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EV34 = ROOT / "docs" / "audits" / "m34-evidence"
OUTDIR = ROOT / "docs" / "audits" / "m35-evidence"
OPEN_STATES = {"UNDER-REVIEW", "EVIDENCE-INCOMPLETE", "OPEN"}

QUESTION = {
    "R-TRUTH-UNKNOWN": ("Is this truthiness test correct for the value it guards?",
                        "the subject's type/optionality is not established by declaration, "
                        "assignment, or a caller contract",
                        "a wrong test silently drops a legitimate value (or accepts a missing one) "
                        "in a calculation the user reads"),
    "R-TRUTH-NUMERIC": ("May this numeric subject be tested for truthiness?",
                        "whether a legitimate zero must be distinguished from a missing value",
                        "zero treated as absent (or vice versa) changes reported quantities"),
    "R-EXC-PASS": ("May this exception be swallowed with `pass`?",
                   "what the swallowed failure hides, and whether the caller/user must learn of it",
                   "an unreported failure can leave the user believing an operation succeeded"),
    "R-PASS-EXC": ("May this handler body be `pass` only?",
                   "same as R-EXC-PASS: the observable consequence of the swallowed failure",
                   "silent failure during save/export/calculation is indistinguishable from success"),
    "R-EXC-SILENT-RETURN": ("Is returning this fallback value without logging correct?",
                            "whether the caller can distinguish 'no data' from 'failure'",
                            "a swallowed failure surfaces as an empty/neutral result in a report"),
    "R-EXC-OTHER": ("Is this exception handling contractually correct?",
                    "the intended failure semantics at this call site",
                    "failures may be reported as successes"),
    "R-DEF-RETURN-NUM": ("Is this numeric default returned to the caller the real value?",
                         "whether the underlying quantity is known-absent or unknown",
                         "a fabricated zero entered as a measurement cannot be told from a real zero"),
    "R-DEF-VALUE-PATH": ("Is this default allowed to reach a consumer?",
                         "whether the consuming contract accepts the defaulted value",
                         "defaulted values can be presented as measured facts"),
    "R-PARAM-ARITH": ("Is arithmetic on this parameter domain-correct?",
                      "the parameter's unit/real domain and whether zero/negative are legal",
                      "wrong arithmetic on engineering parameters produces plausible-looking wrong numbers"),
    "R-RED-ZERO": ("Is this zero reduction correct?",
                   "whether zero is a legal input or a missing measurement",
                   "reductions that absorb missing data report a false total"),
}
DEFAULT_QUESTION = ("Is this behaviour semantically correct for its consumer?",
                    "the governing contract for this construct is not established in-repository",
                    "an incorrect semantic can surface in reports the user treats as facts")


def file_lines(rel: str) -> list[str]:
    try:
        return (ROOT / rel).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def line_of(rel: str, n: int | None) -> str:
    if not n:
        return ""
    lines = file_lines(rel)
    return lines[n - 1].strip() if 1 <= n <= len(lines) else ""


def function_block(rel: str, line: int, span: int = 26) -> list[str]:
    lines = file_lines(rel)
    start = max(0, line - 1)
    # walk back to the enclosing def, then forward for the body window
    for i in range(start, max(-1, start - 200), -1):
        if re.match(r"\s*(?:async )?def \w+", lines[i] if i < len(lines) else ""):
            start = i
            break
    return lines[start:start + span]


def contract_for(rec: dict) -> dict | None:
    """Look for a *stated* contract at the site: comment on the handler, docstring line, or an
    explicit swallow rationale. Returns the quoted evidence or None."""
    rel, line = rec["file"], rec.get("line_m34") or rec.get("line_m33") or 0
    if not line:
        return None
    lines = file_lines(rel)
    if not (1 <= line <= len(lines)):
        return None
    this = lines[line - 1].strip()
    # 1. the construct line itself carries the rationale
    if len(this) > 12 and re.search(r"#", this) and re.search(r"\b(must not|safe|ignore|intentional|"
                                                              r"cleanup|non-fatal|best-effort|optional)",
                                                              this, re.I):
        return {"kind": "inline-comment", "quote": this}
    # 2. the enclosing function documents the failure policy
    block = function_block(rel, line)
    for entry in block:
        if re.search(r'"""', entry) or re.match(r"\s*#", entry):
            if re.search(r"\b(must not|ignored|intentional|non-fatal|best[- ]effort|optional|"
                         r"read-only|not fatal|never raise)\b", entry, re.I):
                return {"kind": "function-docstring-or-comment", "quote": entry.strip()}
    # 3. the handler logs elsewhere: an explicit reporting contract
    window = lines[line - 1: line + 6]
    for entry in window:
        if re.search(r"logger\.(warning|error|exception|info|debug)\(", entry):
            return {"kind": "explicit-reporting", "quote": entry.strip()}
    return None


def main() -> int:
    ledger = json.loads((EV34 / "m34-ledger.json").read_text())
    items = list(ledger["carried_records"]) + list(ledger["new_records"])
    open_items = [i for i in items if i.get("disposition") in OPEN_STATES]

    register = []
    adjudicated = []
    for rec in open_items:
        rel = rec["file"]
        line = rec.get("line_m34") or rec.get("line_m33")
        current_sha = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() if (ROOT / rel).is_file() else None
        q, missing, why = QUESTION.get(rec["rule"], DEFAULT_QUESTION)
        entry = {
            "id": rec["id"],
            "file": rel,
            "line": line,
            "symbol": rec.get("symbol"),
            "kind": rec.get("kind"),
            "rule": rec["rule"],
            "priority": rec.get("priority"),
            "domain": rec.get("domain"),
            "context_fingerprint": rec.get("context_fingerprint"),
            "source_sha256": rec.get("source_sha256"),
            "source_current": current_sha == rec.get("source_sha256"),
            "current_source_line": line_of(rel, line)[:160],
            "question": q,
            "missing_fact": missing,
            "why_it_matters": why,
            "possible_source": _source_hint(rec),
            "classification": "OPEN",
            "confidence": "none",
        }
        contract = contract_for(rec)
        if contract:
            entry["classification"] = "OPEN-CONTRACT-CANDIDATE"
            entry["contract_quote"] = contract
            adjudicated.append({**entry, "evidence_kind": contract["kind"],
                                "evidence_quote": contract["quote"]})
        register.append(entry)

    by_rule = collections.Counter(r["rule"] for r in register)
    by_priority = collections.Counter(r["priority"] for r in register)
    by_domain = collections.Counter(r["domain"] for r in register)
    by_target = collections.Counter(r["possible_source"] for r in register)
    stale = [r["id"] for r in register if not r["source_current"]]

    payload = {
        "schema": "m35-open-item-register",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": "every open ledger record rehydrated against the current tree; no clustering, "
                  "no pattern adjudication",
        "source_ledger_sha256": hashlib.sha256((EV34 / "m34-ledger.json").read_bytes()).hexdigest(),
        "totals": {
            "ledger_records": len(items),
            "open_records": len(register),
            "open_by_rule": dict(by_rule),
            "open_by_priority": dict(by_priority),
            "open_by_domain": dict(by_domain),
            "open_by_evidence_target": dict(by_target),
            "stale_source_records": len(stale),
            "records_with_stated_contract_at_site": len(adjudicated),
        },
        "records": register,
    }
    OUTDIR.mkdir(parents=True, exist_ok=True)
    (OUTDIR / "m35-open-item-register.json").write_text(
        json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    adj = {
        "schema": "m35-contract-adjudications",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": "an item is adjudicated only against a contract quoted from the source at the site; "
                "a quoted contract is a candidate, not an automatic closure",
        "count": len(adjudicated),
        "by_evidence_kind": dict(collections.Counter(a["evidence_kind"] for a in adjudicated)),
        "records": adjudicated,
    }
    (OUTDIR / "m35-contract-adjudications.json").write_text(
        json.dumps(adj, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    print("open records:", len(register), "| by priority:", dict(by_priority))
    print("by rule:", dict(by_rule.most_common(6)))
    print("stale source records:", len(stale))
    print("candidates with a stated contract at the site:", len(adjudicated),
          dict(collections.Counter(a["evidence_kind"] for a in adjudicated)))
    return 0


def _source_hint(rec: dict) -> str:
    rule = rec["rule"]
    if rule.startswith("R-TRUTH") or rule.startswith("R-DEF"):
        return "domain owner: is a missing value distinguishable from a zero at this interface?"
    if rule.startswith("R-EXC") or rule.startswith("R-PASS"):
        return "domain owner: must this failure be reported (log/user message) or is it safely ignored?"
    if rule.startswith("R-PARAM") or rule.startswith("R-RED"):
        return "domain owner: parameter/unit domain and the legal range for this reduction"
    return "domain owner"


if __name__ == "__main__":
    raise SystemExit(main())
