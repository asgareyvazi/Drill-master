# M33 — Semantic Adjudication Closure, Engine-Default Forensics, Evidence Regeneration & Verified Commit Assembly

**Mission 33 semantic audit · 2026-09-27 · branch `arena/01a0c945-drill-master`**
**Base commit `c28bbef37cbac9de7abcfa693e7e21f678fa74ab` · tree `7e16996cdcc1bce4a79fed8823371c20c74eef15`**

> **Verdict: NOT RELEASE-CERTIFIABLE.** The repository-verifiable inventory is **not closed**:
> **2 837 under-review** occurrences and **4 evidence-incomplete** records remain, and the
> 4 external acceptance items (Windows EXE/installer, native Qt, real MinerU/PDF, production
> document acceptance) cannot be executed in this environment. Details and the exact blocking
> counts are in [`M33_RELEASE_CERTIFICATION.md`](M33_RELEASE_CERTIFICATION.md).

This audit answers one question only: *for every pattern occurrence in this source, what is the
evidence-backed disposition?* Every number below is machine-generated into
`docs/audits/m33-evidence/` and every claim is reproducible from the tools listed in
[`M33_EVIDENCE_INDEX.md`](M33_EVIDENCE_INDEX.md). Nothing here repeats an M32 figure without
re-deriving it.

---

## 1. What was tested / adjudicated, and against which source

| Item | Value |
|---|---|
| HEAD at adjudication | `c28bbef37cbac9de7abcfa693e7e21f678fa74ab` |
| Branch | `arena/01a0c945-drill-master` (**LOCAL-ONLY BRANCH — NOT SYNCHRONIZED TO GITHUB**) |
| Worktree delta | 89 modified tracked files + 219 untracked files |
| Sweep scope | source files only (`.py`, `.github/**`, `pyproject.toml`) — 341 files scanned, 3 403 occurrences |
| Inventory | **8934** occurrences, every one with a stable ID, path, line, symbol, pattern, context fingerprint, source sha256 and domain |
| Full suite | **1 818 collected · 1 818 … 0 failed · 0 errors · 4 skipped · 296.8 s · exit 0** (`m33-full-suite-summary.json`, JUnit hash `b7ec010961a0930c891b5ac346965eeaac9e78f105a7a45d7102865f51673e8f`) |
| Mutation controls | **24/24 killed, 0 survivors**, all mutated files byte-identical after the run |

The four skips are the known external dependencies (real DDR xlsx, real DDR pdf/MinerU, real
MinerU, Windows bundle). A skip is not a pass; none of them is counted as verified anywhere in
this document.

## 2. Dispositions (the whole inventory, no sampling)

| Disposition | Count | Meaning |
|---|---|---|
| VERIFIED-CORRECT | 3 712 | the pattern is provably not a defect for this occurrence (guarded, typed, predicated, engine-contracted) |
| INTENTIONAL-BY-DESIGN | 2 264 | a deliberate, evidenced idiom (documented delta/fuel/inventory quantities, sentinel-with-branch, failure-recording handlers, display contracts) |
| **UNDER-REVIEW** | **2837** | **no terminal evidence obtained — open work** |
| REMOVED-WITH-EVIDENCE | 49 | M32 fix items whose pattern no longer exists in the current source, with the removal evidence recorded |
| DEFECT-FIXED | 51 | M32 and M33 fix records whose defect is gone and whose fix is present and hash-verified |
| EXTERNAL-ACCEPTANCE-ONLY | 17 | verifiable only with Windows/real MinerU/production assets |
| EVIDENCE-INCOMPLETE | 4 | 2 × `R-RET-UNPROVEN`, 2 × `R-NOLOCATE` (a record that could not be re-located in the current source) |

Origin: 8 570 carried from the M32 ledger, 96 M32 records whose pattern is gone
(all `ABSENT-REMOVED`), 266 new occurrences from the fresh sweep (proving that a fresh sweep was
necessary: those 266 were not in the M32 inventory).

## 3. Why the 2 837 remain open (and why they were not mass-closed)

The mission forbids closing occurrences on pattern alone, and forbids one root cause
auto-closing hundreds of items. The remaining records need **per-item** facts that this pass did
not obtain. The dominant classes, with what is missing:

| Rule | Count | What a terminal verdict needs |
|---|---|---|
| `R-TRUTH-UNKNOWN` | 963 | the concrete type of the tested subject (repo-wide binding search could not resolve it) — the answer decides "bool flag" vs "missing value treated as false" |
| `R-DEF-UNKNOWN` | 339 | the default/caller contract of the function whose argument default is in question |
| `R-SEL-UNPROVEN` | 217 | whether the `.first()` result is dereferenced without a guard — these are potential `AttributeError` sites, not stylistic noise |
| `R-TRUTH-NUMERIC` | 215 | whether a numeric value legitimately may be `0` (domain) or must be distinguished from missing |
| `R-RET-ONLY-SENTINEL` | 189 | whether the single-sentinel-return function's sentinel is handled by its callers |
| `R-RET-UNPROVEN` / `R-RED-UNPROVEN` | 153 / 126 | caller handling on non-repository paths |
| `R-EXC-PASS` and friends | 104 | per-handler judgement whether the swallow is defensible |

Everything the pass *could* prove was proven: two new per-item rules were added during this
mission (`R-EXC-EXPLICIT-FAILURE`, `R-EXC-RECORDED-SKIP`, `R-PASS-RECORDED`) which closed 195
records with the handler body itself as the evidence — e.g. `except EngineeringError as exc:
return failed(str(exc))` returns an explicit failure object, and `except …: skipped.append(…);
continue` records the skip. Handlers that are genuinely silent were **not** closed.

## 4. What changed in the source during M33

Three evidenced fixes, all mutation-controlled, all with before/after hashes:

| Fix | File | Pre-fix sha256 | Post-fix sha256 | Evidence |
|---|---|---|---|---|
| M33-FIX-01 — data-quality 24 h coverage: a missing duration is unknown, not 0 h | `core/data_quality.py` | `9ebc926f…` (= HEAD) | `0151a92768ec15d1d26c3e81890c5cd2aad2479b12b97b3c00d2eff92a7ba9cc` | 4 S29 tests; mutants killed; coverage/summary/dashboard semantics |
| M33-FIX-02 — casing combined collapse must not echo an absent load as a measured zero | `core/engineering/engines/casing.py` | `caec140b…` (= HEAD) | `17eb484b1a0957129ea7e45b7101702b9c9d09b99f9263c6cb7a8c097a30e545` | 6 new tests; 81-case regression re-run; mutants `E-CASING-ECHO/WARN`, `E-W13-FORMAT` killed |
| M33-FIX-03 — W3 derived displays must not silently clamp a computed ROP to Qt's 99.99 | `tabs/w3_drilling_report.py` (+ `tabs/w13_Engineering_Calculator.py` for the None rendering) | `fd6eca6c…` (Part A) / `5b200e73…` | `e2764c18e975670539ef409b5bf931271510191a9581a406a8db8f3dc4e427a0` / `4fd94858f423a09793e7afaf0f40e346c9bab046d39bfe49faab4aad340f4bee` | pre-fix failure captured verbatim (`truncated to 99.99 (engine returned 150.0)`); mutants `E-W3-CLAMP-MAX/GUARD/BOUND` killed; domain bound taken from `core/validators.py` |

Full forensics, including the two candidates that were **not** changed and why, are in
[`M33_ENGINE_DEFAULTS.md`](M33_ENGINE_DEFAULTS.md).

## 5. Integrity incident carried forward

`M33-INC-001`: `core/professional_export.py` was found holding only the *comment* of an M32 fix
(comment-only variant `4a3d5b44…`); the full fix was re-applied and hash-verified
(`96878cf6…`). Mechanism unattributed; the lesson applied everywhere since — **every "fixed" file
is hash-checked against its recorded post-fix sha256**, and the three M33 fixes carry their
pre-fix hashes (recovered from the Part-A manifest where the file was dirty then, from HEAD
where it was clean).

## 6. Evidence integrity (Part U/V/W)

- All adjudication evidence was **regenerated after the last source edit** (sweep → reconciliation
  → ledger → matrix → instruments), so no record cites a stale line: each carries the sha256 of
  the file it was adjudicated against.
- `m33-evidence-manifest.json` records size, sha256 and a classification for every audit artifact
  and document: **364 files / 51.1 MB**, of which 8 are ≥1 MB (`giant_files`), every one
  classified before any dedup consideration — no large evidence file was deleted or
  de-duplicated, because provenance would be lost.
- `m33-doc-claim-audit.json` classifies all 84 markdown documents: 18 living documents corrected to
  the M33 numbers, 5 dated mission records given a HISTORICAL banner, 61 left untouched (no stale
  claim), 0 removed, 0 with an invented SHA.

## 7. Commit readiness (Parts S/T)

A staging simulation built the two candidate commits with a throwaway index and `git commit-tree`
(no branch, ref or HEAD was moved — recorded in `m33-commit-staging-simulation.json`):

| Candidate | SHA | Tree | Files staged | Content |
|---|---|---|---|---|
| Commit 1 — semantics | `a9d7dede612b9c5c86de8eea5555a969811cc77a` | `dc5939c8…` | 87 | source + tests + packaging/config + `.github/workflows/ci.yml`, including the two previously-untracked modules `core/operational_time.py`, `core/safety_semantics.py`; **no audit document** |
| Commit 2 — records | `b1fca5dac4181f16e0aa9c52de6c6b96369a7178` | `c51a0d1a…` | 222 | audit records, M27–M32/M33 evidence, corrected living docs |

Commit 1 was exported with `git archive` into a directory with **no `.git`** and no untracked
file, then verified there: `compileall` clean, **1 818 tests collected** (same count as the
worktree), and the full suite re-run inside that tracked-only tree — the result is recorded in
`M33_RELEASE_CERTIFICATION.md`. That is the proof that the shipped source no longer depends on
untracked files.

## 8. What this audit does **not** claim

- It does not claim the 2 837 under-review occurrences are safe, benign, or "probably fine".
- It does not claim Windows, native Qt, real MinerU or production-document acceptance.
- It does not claim CI is green: the session branch does not exist on the remote
  (**LOCAL-ONLY BRANCH — NOT SYNCHRONIZED TO GITHUB**), so no run for this source can exist.
- It does not claim the four external items can be closed by anything done here.
