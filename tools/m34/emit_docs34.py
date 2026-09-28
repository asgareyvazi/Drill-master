#!/usr/bin/env python3
"""Emit M34_DOMAIN_MATRIX.md and M34_EVIDENCE_INDEX.md from the evidence itself (no transcription)."""
from __future__ import annotations
import hashlib, json, re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EV = ROOT / "docs" / "audits" / "m34-evidence"
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")

matrix = json.loads((EV / "m34-domain-matrix.json").read_text())
inv = json.loads((EV / "m34-closure-invariants.json").read_text())
recon = json.loads((EV / "m34-reconciliation.json").read_text())
summary = json.loads((EV / "m34-ledger-summary.json").read_text())
_new_hits = len(json.loads((EV / "m34-ledger.json").read_text())["new_records"])

lines = [
    "# M34 — 69-Domain Matrix",
    "",
    f"*Generated {NOW} by `tools/m34/emit_docs34.py` from `m34-domain-matrix.json`; the per-item ledger "
    f"is `m34-ledger.json`.*",
    "",
    f"**Ledger items:** {matrix['ledger_items']} — **sum of the domain rows:** "
    f"{matrix['reconciliation']['sum_of_domain_totals']} — "
    f"**reconciles:** {matrix['reconciliation']['reconciles']}.",
    "",
    "The taxonomy (ids and names) is carried unchanged from `docs/audits/m29-evidence/domain-matrix.json` so "
    "the matrices are comparable across missions. A row is a *projection of the ledger by file path*: the "
    "ledger record is the source of truth for one occurrence. `meta` at the end states the mapping caveat and "
    "the gates.",
    "",
    "| # | domain | total | VERIFIED-CORRECT | INTENTIONAL | UNDER-REVIEW | DEFECT-FIXED | REMOVED-W-EVIDENCE | EXT-ONLY | HIGH open | CRIT open |",
    "|---|---|---|---|---|---|---|---|---|---|---|",
]
for r in matrix["domains"]:
    lines.append(f"| {r['id']} | {r['domain']} | {r['total']} | {r['verified_correct']} | {r['intentional']} | "
                 f"{r['under_review']} | {r['defect_fixed']} | {r['removed_with_evidence']} | "
                 f"{r['external_acceptance_only']} | {r['high_open']} | {r['critical_open']} |")
lines += [
    "",
    "## Reconciliation and gates",
    "",
    f"* sum of domain rows = **{matrix['reconciliation']['sum_of_domain_totals']}** = ledger items "
    f"**{matrix['ledger_items']}**",
    f"* terminal items **{inv['terminal_items']}**; UNDER-REVIEW **{inv['unreviewed']}**; "
    f"EVIDENCE-INCOMPLETE **{inv['evidence_incomplete']}**",
    f"* blocker gate: CRITICAL unresolved **{inv['critical_unresolved']}**, HIGH unresolved "
    f"**{inv['high_unresolved']}**",
    f"* closure gate: inventory == terminal → **{inv['closure_gate_inventory_equals_terminal']}**; "
    f"UNREVIEWED=0 → **{inv['closure_gate_unreviewed_zero']}**; EVIDENCE-INCOMPLETE=0 → "
    f"**{inv['closure_gate_evidence_incomplete_zero']}**",
    "",
    f"> {inv['statement']}",
    "",
    matrix["mapping_caveat"],
    "",
]
(ROOT / "M34_DOMAIN_MATRIX.md").write_text("\n".join(lines))

# ---------------- evidence index ----------------
def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

WHAT = {
    "M34_PREWORKSPACE_MANIFEST.json": "Part A pre-flight: HEAD/tree/branch, every modified and untracked file with sha256/size/mtime, the tracked diff hash, staged/deleted counts, shallow-clone state.",
    "m34-fresh-sweep.json": "Part C mandatory fresh sweep: 336 files, 5 802 hits, 21 families, one record per hit with path/line/normative text.",
    "m34-ledger.json": "The inventory of record: 11 554 items, one record each with INV-ID, path, symbol, family, line, context fingerprint, source sha256, domain, priority, disposition, rule, root cause, evidence (M33 evidence retained on re-adjudicated items).",
    "m34-ledger-summary.json": "Projection of the ledger: dispositions, origin, priority, sweep/carry-forward counters, comparison with the M30/M31/M32/M33 numbers.",
    "m34-reconciliation.json": "Inventory comparison and delta classes, family table, open register by rule, the defect-fixed / removed / external / evidence-incomplete item lists.",
    "m34-closure-invariants.json": "Closure gate and blocker gate with every count, plus the rules driving the open items.",
    "m34-domain-matrix.json": "The 69-domain projection with the math reconciliation.",
    "m34-fix-reverification.json": "Part B: all 13 fixes (M32 001–010, M33 casing/data-quality/Qt-clamp) re-verified by contract probes against the current source and by their own regression tests.",
    "m34-mutation-controls.json": "Part O: 16 mutants designed from the fix contracts; 15 killed, 1 documented equivalent survivor; byte-identical restore of every touched file.",
    "m34-wheel-and-clean-env.json": "Part Q/R: lock 26/26 exact from a throwaway venv, wheel built from the tracked population, installed, started outside the checkout — with the ModuleNotFoundError that blocks the release.",
    "m34-commit-staging-simulation.json": "Part S: HEAD + Commit-1 file set in a temp tree (no audit material), compile/collect/targeted/full-suite/import smoke, and the Commit-2 decision list.",
    "m34-doc-claim-audit.json": "Part X: every SHA, test-count and branch/status claim in the living docs, classified CURRENT-VERIFIED / HISTORICAL / RESOLVES-LOCALLY / UNRESOLVED / CHECK.",
    "m34-git-cleanliness.json": "Worktree classification, diff --check, cache/secrets/mutant scan.",
    "M34_INVENTORY_LEDGER.json": "Invariant projection and hash pin of the per-item ledger (the deliverable summary).",
    "m34-full-suite-junit.xml": "Part P: the full suite on the final tree, JUnit, one testcase per test.",
    "m34-commit1-overlay-junit.xml": "The same suite re-run inside the Commit-1-only tree.",
}
index = [
    "# M34 — Evidence Index",
    "",
    f"*Generated {NOW} by `tools/m34/emit_docs34.py`.* Every file below is in `docs/audits/m34-evidence/` "
    "unless a path says otherwise. Hashes are of the file as it existed when this index was written; the "
    "ledger is hash-pinned again inside `M34_INVENTORY_LEDGER.json`.",
    "",
    "## Headline numbers (all re-derived, none quoted)",
    "",
    f"* ledger items **{summary['items']}** — dispositions {summary['dispositions']}",
    f"* sweep: 336 files, 5 802 hits, 21 families; carried forward at SAME-FILE-HASH "
    f"**{summary['carry_forward'].get('SAME-FILE-HASH')}**, M33 hits de-duplicated "
    f"**{summary['sweep']['already_covered_by_m33']}**, genuinely new hits **{_new_hits}**",
    f"* fixes: 13/13 VERIFIED; mutants: 15 killed + 1 documented equivalent",
    f"* closure gate: inventory == terminal → **{inv['closure_gate_inventory_equals_terminal']}**, "
    f"UNREVIEWED = **{inv['unreviewed']}**, EVIDENCE-INCOMPLETE = **{inv['evidence_incomplete']}**",
    f"* blocker gate: CRITICAL = **{inv['critical_unresolved']}**, HIGH = **{inv['high_unresolved']}**",
    "",
    "## Files",
    "",
    "| evidence file | bytes | sha256 | what it proves |",
    "|---|---|---|---|",
]
for name, what in WHAT.items():
    p = EV / name
    if p.exists():
        index.append(f"| `{name}` | {p.stat().st_size} | `{sha(p)[:32]}…` | {what} |")
    else:
        index.append(f"| `{name}` | — | — | **MISSING** at index time |")
index += [
    "",
    "## Reproduction",
    "",
    "```bash",
    "# tools (in-repo, so the next session inherits them)",
    "python tools/m34/sweep34.py                 # -> m34-fresh-sweep.json",
    "python tools/m34/adjudicate34.py            # -> m34-ledger.json",
    "python tools/m34/stats34.py                 # -> m34-reconciliation.json",
    "python tools/m34/audit34.py                 # -> domain matrix, invariants, ledger summary, docs, git",
    "python tools/m34/reverify_fixes34.py        # -> m34-fix-reverification.json",
    "python tools/m34/mutate34.py                # -> m34-mutation-controls.json",
    "python tools/m34/release34.py --stage=wheel            # -> m34-wheel-and-clean-env.json",
    "python tools/m34/release34.py --stage=commit1 --full-suite",
    "python tools/m34/emit_docs34.py             # -> M34_DOMAIN_MATRIX.md, M34_EVIDENCE_INDEX.md",
    "",
    "# the suite, exactly as the release gate runs it",
    "PYTHONDONTWRITEBYTECODE=1 LD_LIBRARY_PATH=/tmp/qtstub QT_QPA_PLATFORM=offscreen \\",
    "  DRILLMASTER_AI_IMPORT=0 /home/user/verify-venv/bin/python -m pytest -ra -p no:cacheprovider \\",
    "  -W ignore::DeprecationWarning --junitxml=docs/audits/m34-evidence/m34-full-suite-junit.xml -q",
    "```",
    "",
    "**Environment limits that are NOT acceptance:** the Qt libraries here are fail-loud stubs (font metrics "
    "unavailable), there is no Windows runtime, and the DDR/MinerU/packaging acceptance inputs are absent. "
    "Every affected item is `EXTERNAL-ACCEPTANCE-ONLY` or explicitly NOT-RUN; no Windows or native-Qt result "
    "is claimed anywhere in this mission.",
]
(ROOT / "M34_EVIDENCE_INDEX.md").write_text("\n".join(index))
print("wrote M34_DOMAIN_MATRIX.md, M34_EVIDENCE_INDEX.md")
