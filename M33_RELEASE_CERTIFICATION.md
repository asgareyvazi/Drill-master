# M33 — release decision and audit answers

**Mission 33 · 2026-09-27 · branch `arena/01a0c945-drill-master` · base commit `c28bbef37cbac9de7abcfa693e7e21f678fa74ab`**

> ## Verdict: **NOT RELEASE-CERTIFIABLE**
>
> The semantic closure is **incomplete for repository-verifiable code**, therefore none of the
> three "complete" states can be claimed. This is **not** an external-only rejection, and it is
> **not** a claim that the tree is broken: it is a statement that **2 837 occurrences are still
> `UNDER-REVIEW`** and **4 records are `EVIDENCE-INCOMPLETE`**, with 834 of the open records
> carrying priority HIGH. Until those are terminally dispositioned, the mission's own gate
> (`UNREVIEWED = 0`, `EVIDENCE-INCOMPLETE = 0`, CRIT = 0, HIGH = 0 for repo-verifiable items)
> cannot be satisfied. Windows EXE/installer, native Qt, real MinerU/PDF and production-document
> acceptance remain **external and unexecuted**.

## Verified execution boundary

| Check | Observed result (this run, this source) |
|---|---|
| Tested source | worktree of `c28bbef37cbac9de7abcfa693e7e21f678fa74ab` + 89 modified / 219 untracked files (the M33 delivery set) |
| Branch | `arena/01a0c945-drill-master` — **LOCAL-ONLY BRANCH — NOT SYNCHRONIZED TO GITHUB** (verified by `gh api` at mission start: no such ref on the remote) |
| Fresh sweep | 341 source files scanned, **3 403** occurrences (`m33-fresh-sweep.json`) |
| Inventory | **8934** occurrences = 8 570 carried + 96 M32-absent + 266 new + 2 forensic-found defects (`M33_INVENTORY_LEDGER.json`) |
| Full suite | **1 818 collected · 0 failed · 0 errors · 4 skipped · 296.8 s · exit 0** — JUnit `b7ec010961a0930c891b5ac346965eeaac9e78f105a7a45d7102865f51673e8f` |
| Skipped (4, classified) | real DDR xlsx acceptance, real DDR pdf/MinerU, real MinerU, Windows bundle smoke — all external assets, none counted as a pass |
| Environment | Linux, Python 3.11 (verify-venv), pytest 9.1.1, ruff 0.16.6, build 1.6.1, PySide6 6.8.1.1 offscreen with declared fail-loud stubs (`LD_LIBRARY_PATH=/tmp/qtstub`), `DRILLMASTER_AI_IMPORT=0` |
| Compile | `compileall` PASS on the worktree and on the exported commit-1 tree |
| Lint gate | `ruff --select E722,F821` PASS; total debt **5 338 ≤ 5 375** ceiling (debt, not clean) |
| Lock | 26 locked distributions at exact locked versions, 0 mismatches, `pip check` clean |
| Wheel | `drillmaster-1.0.0-py3-none-any.whl`, 1 036 779 B, sha256 `af999abbdc70e1d8ad4a1bec6c6bcf4e0e255f7b32ac271b0b0709c92219c26b`, built from the **commit-1 staging tree** |
| Outside-checkout run | PASS: installed into an isolated target, imported and `app.run_package_smoke()` returned 0 with the checkout **not** on `sys.path` (`m33-wheel-and-clean-env.json`) |
| Tracked-only proof | commit-1 tree exported with `git archive` (no `.git`, 1 818 tests collected) and the **full suite re-run inside it: 1 818 / 0 failed / 0 errors / 4 skipped / 285.6 s / exit 0** — the two previously-untracked modules `core/operational_time.py`, `core/safety_semantics.py` are tracked in that commit |
| Mutation controls | **24/24 killed, 0 survivors**; every mutated file restored byte-identically (`m33-mutation-controls.json`) |
| CI for this source | **UNAVAILABLE** — the branch does not exist on the remote, so no run can exist. Local green ≠ CI green. |
| Native Qt / Windows / MinerU / production documents | **NOT-RUN / EXTERNAL-BLOCKED** (no system libGL/libEGL/libxkbcommon/libdbus here; no Windows host; no real MinerU assets) |

Reproduction (from the repository root, with the locked environment and the declared Qt stubs):

```bash
QT_QPA_PLATFORM=offscreen LD_LIBRARY_PATH=/tmp/qtstub DRILLMASTER_AI_IMPORT=0 \
/home/user/verify-venv/bin/python -m pytest tests -q -p no:cacheprovider \
  --junitxml=docs/audits/m33-evidence/m33-full-suite-junit.xml
/home/user/verify-venv/bin/python /home/user/m33-tools/sweep_source.py
/home/user/verify-venv/bin/python /home/user/m33-tools/reconcile.py
/home/user/verify-venv/bin/python /home/user/m33-tools/adjudicate33.py
/home/user/verify-venv/bin/python /home/user/m33-tools/invariants33.py
```

## Closure invariants (Part Z, machine-computed)

| Invariant | Required | Observed | Status |
|---|---|---|---|
| inventory N = sum of dispositions | true | 8934 = 8934 | PASS |
| every record has ID / context fingerprint / source sha | true | true / true / true | PASS |
| UNREVIEWED | 0 | 0 | PASS |
| UNDER-REVIEW | 0 | **2837** | **FAIL** |
| EVIDENCE-INCOMPLETE (repo-verifiable) | 0 | **4** (2 `R-RET-UNPROVEN`, 2 `R-NOLOCATE`) | **FAIL** |
| CRITICAL unresolved | 0 | 0 | PASS |
| HIGH unresolved | 0 | **834** | **FAIL** |
| Only external acceptance remaining | true | false | **FAIL** |

Source: `docs/audits/m33-evidence/m33-closure-invariants.json`.

## What was fixed in this mission (each with pre-fix and post-fix hashes)

| Fix | File | Effect | Control |
|---|---|---|---|
| M33-FIX-01 | `core/data_quality.py` | 24 h coverage with any unrecorded duration is **unknown**, not 0 h; summary excludes unknowns and reports `confidence`; dashboard averages known metrics only | 4 S29 tests + mutants |
| M33-FIX-02 | `core/engineering/engines/casing.py` | an *absent* axial tension / internal pressure is no longer echoed as a measured `0.0` / `fyax`; explicit zero still is; unsupplied reductions are warned about | 6 new tests + 81-case regression re-run + 3 mutants |
| M33-FIX-03 | `tabs/w3_drilling_report.py` (+ `tabs/w13_Engineering_Calculator.py`) | a computed ROP is no longer silently truncated to Qt's 99.99 in the display, the payload or the persisted row; the field declares the validator's 0–500 domain bound | pre-fix failure captured verbatim + 2 new tests + 3 mutants |

`M33-INC-001` (a fixed file found holding only its comment) was re-applied and hash-verified; the
mechanism is recorded as unattributed rather than guessed.

## Audit answers (Part AC)

The Mission 33 brief's verbatim 50-question list is **not present in the workspace and not
recoverable from this session's context** (searched: no file in the tree contains it). Inventing
fifty questions would be a fabricated deliverable, so what follows answers the question set the
brief's own parts A–AB imply, numbered sequentially; if the verbatim list is supplied, each item
maps 1:1 and any question not covered is to be treated as `EVIDENCE-INCOMPLETE` rather than
assumed answered.

1. **Git identity audited?** Branch `arena/01a0c945-drill-master`, base `c28bbef37cbac9de7abcfa693e7e21f678fa74ab`, tree `7e16996cdcc1bce4a79fed8823371c20c74eef15`; `HEAD^` unresolvable (shallow/grafted, `.git/shallow` = {02053eb, c28bbef}); no stash; 89 modified + 219 untracked at capture.
2. **Is the branch published?** No. `gh api` at mission start shows no such ref on `origin` → **LOCAL-ONLY BRANCH — NOT SYNCHRONIZED TO GITHUB**. No push was attempted from this session; no CI run can exist for this source.
3. **Was the M32 report taken on trust?** No. Every M32 number was re-derived (fresh sweep, reconciliation, ledger). The M32 ledger was loaded as *input data* (8 666 records) and each record was re-located in the current source or classified `ABSENT-REMOVED` (96; `MATCHED-TAIL` recovered 377, i.e. line movement is not removal).
4. **Was a fresh sweep performed before closure?** Yes — 341 source files, 14 families, 3 403 occurrences, after the last source edit; 266 hits were new relative to M32, proving the earlier inventory was incomplete.
5. **Can any item be closed on pattern alone?** No. Every disposition carries a per-item evidence string (subject type, consumer kind, handler body, caller analysis, engine contract, or consumer in file). Items whose fingerprint could not be re-located are `EVIDENCE-INCOMPLETE`, not "gone".
6. **M32-FIX-001…010 re-verified?** Yes: each fix's marker is present in the **current** file, file hashes recorded, the twelve targeted M32 regression tests re-run green, and the M32 mutants re-run killed (`m33-m32-fix-reverification.json`).
7. **Any M32 fix found missing?** Yes — `M33-INC-001` (`core/professional_export.py` comment-only); re-applied and hash-verified. No other fix was found missing.
8. **Engine-default candidates resolved?** Yes, all five (`M33_ENGINE_DEFAULTS.md`): two `VALID DOMAIN LIMIT` (T&D WOB in the engine and in the snapshot — the engine's own signature declares 0.0 and has no unknown state; nothing echoes it), three `BUG` (data quality, casing echo, W3 clamp).
9. **Was the 99.99 clamp "fixed" with a magic number?** No. It was diagnosed as Qt's `QDoubleSpinBox` default (nobody set 99.99); the domain bound now comes from `core/validators.py` (`avg_rop` 0–500) and the display refuses to truncate beyond any bound instead of inventing a new ceiling.
10. **Does the fix change physics?** No: for casing, the ratings, regimes, D/t and safety factors are numerically identical to the pre-fix run; the change is the *reported inputs* and a warning. For data quality, the change is a third state (unknown) alongside known/zero.
11. **Are missing and explicit zero distinguishable after the fixes?** Yes, and it is now asserted by tests: `None` (not recorded) vs `0.0` (recorded zero) in the casing result, in the data-quality metric, and in the drill-string payload.
12. **Domain sweeps F–M performed?** Partially, with exact residuals: NULL/zero secondary sweep is folded into the ledger's buckets (2 837 open, listed by rule and file in `M33_INVENTORY_LEDGER.json`); time semantics (G), engineering input contracts (H), UI/persistence boundary (I), exporter comparison (J), snapshot integrity (K), data-quality audit (L) and the error-handling re-sweep (M) are represented by the `R-EXC-*`, `R-SEL-*`, `R-DEF-*`, `R-RED-*` and `R-TRUTH-*` records — **not all of which reached a terminal verdict**, which is precisely why the verdict is not certified.
13. **False-success paths (M)?** The `R-EXC-*` family is the answer; two new per-item rules closed 195 handlers that *state* the failure (`return failed(...)`, counters, warnings lists, logger, error labels). Handlers that swallow silently remain `UNDER-REVIEW` — none was waved through.
14. **Regression/adversarial tests for each closure (N)?** Every rule-level closure is backed by the rule's per-item evidence and by the mutation matrix; the three code fixes have dedicated tests that fail on the pre-fix source. Structurally-closed items (e.g. removal with evidence) are exempt as the brief allows.
15. **Mutation controls (O)?** 24/24 killed, including the 13 M32 controls re-run independently and 9 new Part-E mutants; one first-pass survivor (`E-W3-CLAMP-BOUND`) was treated as a real coverage gap, closed by adding the missing assertion, and recorded — not hidden.
16. **Full-suite health (P)?** 1 818 collected / 0 failed / 0 errors / 4 skipped / 296.8 s / exit 0, with JUnit XML and a parsed summary including environment and scope caveats.
17. **Exact lock (Q)?** 26 locked distributions verified at their exact locked versions, 0 mismatches, `pip check` clean; no lock file was changed in this mission.
18. **Wheel + outside-checkout run (R)?** Built from the commit-1 tree, installed into an isolated target, imported and smoke-run with the checkout absent from `sys.path`; the wheel carries the M33 fixes.
19. **Tracked-only dependency proof (R)?** The commit-1 tree was exported with `git archive` (no `.git`, no untracked file) and the **full suite re-ran green in it (1 818/0/0/4)**; `core/operational_time.py` and `core/safety_semantics.py` are in that commit.
20. **Commit staging simulated (S/T)?** Yes: commit 1 = 87 files (source + tests + packaging/config + CI workflow, no audit document) `a9d7dede612b9c5c86de8eea5555a969811cc77a`; commit 2 = 222 files (audit records, evidence, corrected living docs) `b1fca5dac4181f16e0aa9c52de6c6b96369a7178`; both created with a throwaway index and `commit-tree`, with HEAD, refs and branches provably unmoved. Nothing was committed or pushed by this session.
21. **Evidence regenerated against the final source (U)?** Yes — sweep, reconciliation, ledger, matrix, invariants, doc-claim audit and evidence manifest were all produced after the last source edit; each ledger record carries the `source_sha256` it was adjudicated against.
22. **Was the evidence itself verified (V/W)?** Yes: per-file sha256/size/provenance in `m33-evidence-manifest.json` (364 files, 51.1 MB, 8 giant files classified — none deleted or de-duplicated, because provenance would be lost).
23. **Living documents (X)?** 84 markdown documents audited: 18 living documents corrected to the M33 numbers, 5 dated mission records given a HISTORICAL banner, 61 untouched; 0 removed; no SHA invented anywhere.
24. **Domain matrix (Y)?** 69 domains reconciled; the sum invariant holds (in-taxonomy 2 833 + shared-core-source 6 101 = 8 934). Most M29 domains list *shared* core modules, so those occurrences are reported in an explicit shared row rather than credited to one domain; 36 domains have no exclusively-claimed occurrence — which is **not** a coverage claim.
25. **Was anything deleted?** No. No file, branch or evidence artifact was deleted in this session.
26. **Is any claim external-only while repo work remains?** No: the verdict is "not certifiable" **because repository-verifiable work remains** (2 837 under review, 834 HIGH, 4 evidence-incomplete), independent of the external items.
27. **What would close the remaining work?** Per-record domain facts: the concrete type of the tested subject for `R-TRUTH-UNKNOWN` (963), the default/caller contract for `R-DEF-UNKNOWN` (339), guard analysis for `R-SEL-UNPROVEN` (217), caller-handling proof for `R-RET-ONLY-SENTINEL`/`R-RET-UNPROVEN` (342 combined), and the per-handler judgement for `R-EXC-PASS` and friends (104). The full ordered list with file/line/ID is in `M33_INVENTORY_LEDGER.json` → `open_residual`.
28. **Is anything in this document unpublished or unreproducible?** The branch is local-only, so the *artifacts* are not on the remote; every number here is reproducible from the tools and evidence files in the workspace (index: `M33_EVIDENCE_INDEX.md`). CI green is not claimed and cannot be claimed from here.

## Verdict rationale (Part AD)

The mission allows exactly four states. `RELEASE-CERTIFIABLE` requires complete semantic closure,
zero unresolved repository critical/high items, coherent evidence and reproducible current source.
Closure is incomplete (2 837 under review, 834 of them HIGH, 4 evidence-incomplete), so the
remaining possibilities are the three "not certifiable" states. Because the blockers are
**repository-verifiable** (not external acceptance), the correct state is:

> **NOT RELEASE-CERTIFIABLE — semantic inventory not closed for repository-verifiable code**
> (2 837 `UNDER-REVIEW`, 834 HIGH, 4 `EVIDENCE-INCOMPLETE`), with the four external acceptance
> items additionally unexecuted.
