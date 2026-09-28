# M34 — Evidence Index

*Generated 2026-09-27T12:28:29+00:00 by `tools/m34/emit_docs34.py`.* Every file below is in `docs/audits/m34-evidence/` unless a path says otherwise. Hashes are of the file as it existed when this index was written; the ledger is hash-pinned again inside `M34_INVENTORY_LEDGER.json`.

## Headline numbers (all re-derived, none quoted)

* ledger items **11554** — dispositions {'INTENTIONAL-BY-DESIGN': 2880, 'VERIFIED-CORRECT': 7333, 'UNDER-REVIEW': 1224, 'DEFECT-FIXED': 51, 'EXTERNAL-ACCEPTANCE-ONLY': 17, 'REMOVED-WITH-EVIDENCE': 49}
* sweep: 336 files, 5 802 hits, 21 families; carried forward at SAME-FILE-HASH **8933**, M33 hits de-duplicated **3182**, genuinely new hits **2620**
* fixes: 13/13 VERIFIED; mutants: 15 killed + 1 documented equivalent
* closure gate: inventory == terminal → **False**, UNREVIEWED = **1224**, EVIDENCE-INCOMPLETE = **0**
* blocker gate: CRITICAL = **0**, HIGH = **371**

## Files

| evidence file | bytes | sha256 | what it proves |
|---|---|---|---|
| `M34_PREWORKSPACE_MANIFEST.json` | 80800 | `0312cebd111c1e608ee93d02a67c4546…` | Part A pre-flight: HEAD/tree/branch, every modified and untracked file with sha256/size/mtime, the tracked diff hash, staged/deleted counts, shallow-clone state. |
| `m34-fresh-sweep.json` | 2304353 | `05ef7d7fcfdeae6fed94537bcb9bcbbd…` | Part C mandatory fresh sweep: 336 files, 5 802 hits, 21 families, one record per hit with path/line/normative text. |
| `m34-ledger.json` | 11394989 | `d81a77bda0330c75493f4081c4a02e4d…` | The inventory of record: 11 554 items, one record each with INV-ID, path, symbol, family, line, context fingerprint, source sha256, domain, priority, disposition, rule, root cause, evidence (M33 evidence retained on re-adjudicated items). |
| `m34-ledger-summary.json` | 1516 | `afb9c91ac9fe33ee2dcae6ac7fe9a6ef…` | Projection of the ledger: dispositions, origin, priority, sweep/carry-forward counters, comparison with the M30/M31/M32/M33 numbers. |
| `m34-reconciliation.json` | 43107 | `2c24b1ed18c72057a43c6e17c8728358…` | Inventory comparison and delta classes, family table, open register by rule, the defect-fixed / removed / external / evidence-incomplete item lists. |
| `m34-closure-invariants.json` | 2721 | `732ac8b5251ef26d9982c71111eaa860…` | Closure gate and blocker gate with every count, plus the rules driving the open items. |
| `m34-domain-matrix.json` | 30649 | `55177bf06c3f678b37ef529b672e52b2…` | The 69-domain projection with the math reconciliation. |
| `m34-fix-reverification.json` | 15699 | `8f3b0f1420b46f43136e23a17b6e9e92…` | Part B: all 13 fixes (M32 001–010, M33 casing/data-quality/Qt-clamp) re-verified by contract probes against the current source and by their own regression tests. |
| `m34-mutation-controls.json` | 14715 | `e97b1e964842f39fbf45acd24da8980b…` | Part O: 16 mutants designed from the fix contracts; 15 killed, 1 documented equivalent survivor; byte-identical restore of every touched file. |
| `m34-wheel-and-clean-env.json` | 3311 | `e2f95c5ce71998af4ed0cb797f7bf2f9…` | Part Q/R: lock 26/26 exact from a throwaway venv, wheel built from the tracked population, installed, started outside the checkout — with the ModuleNotFoundError that blocks the release. |
| `m34-commit-staging-simulation.json` | 64165 | `ed98582e960982f3c33a1327751581fb…` | Part S: HEAD + Commit-1 file set in a temp tree (no audit material), compile/collect/targeted/full-suite/import smoke, and the Commit-2 decision list. |
| `m34-doc-claim-audit.json` | 43787 | `037cad363a402aec0c9465061e160df3…` | Part X: every SHA, test-count and branch/status claim in the living docs, classified CURRENT-VERIFIED / HISTORICAL / RESOLVES-LOCALLY / UNRESOLVED / CHECK. |
| `m34-git-cleanliness.json` | 1776 | `f9f902f263ed2a44c5b25153122f1b52…` | Worktree classification, diff --check, cache/secrets/mutant scan. |
| `M34_INVENTORY_LEDGER.json` | 3335 | `5732aaa25bb50d64386663df58f3cdd8…` | Invariant projection and hash pin of the per-item ledger (the deliverable summary). |
| `m34-full-suite-junit.xml` | 238035 | `5f317f4105478fb4feb28489f9b6e137…` | Part P: the full suite on the final tree, JUnit, one testcase per test. |
| `m34-commit1-overlay-junit.xml` | 238063 | `f432bb835c2dde6be7afc86f0d68185c…` | The same suite re-run inside the Commit-1-only tree. |

## Reproduction

```bash
# tools (in-repo, so the next session inherits them)
python tools/m34/sweep34.py                 # -> m34-fresh-sweep.json
python tools/m34/adjudicate34.py            # -> m34-ledger.json
python tools/m34/stats34.py                 # -> m34-reconciliation.json
python tools/m34/audit34.py                 # -> domain matrix, invariants, ledger summary, docs, git
python tools/m34/reverify_fixes34.py        # -> m34-fix-reverification.json
python tools/m34/mutate34.py                # -> m34-mutation-controls.json
python tools/m34/release34.py --stage=wheel            # -> m34-wheel-and-clean-env.json
python tools/m34/release34.py --stage=commit1 --full-suite
python tools/m34/emit_docs34.py             # -> M34_DOMAIN_MATRIX.md, M34_EVIDENCE_INDEX.md

# the suite, exactly as the release gate runs it
PYTHONDONTWRITEBYTECODE=1 LD_LIBRARY_PATH=/tmp/qtstub QT_QPA_PLATFORM=offscreen \
  DRILLMASTER_AI_IMPORT=0 /home/user/verify-venv/bin/python -m pytest -ra -p no:cacheprovider \
  -W ignore::DeprecationWarning --junitxml=docs/audits/m34-evidence/m34-full-suite-junit.xml -q
```

**Environment limits that are NOT acceptance:** the Qt libraries here are fail-loud stubs (font metrics unavailable), there is no Windows runtime, and the DDR/MinerU/packaging acceptance inputs are absent. Every affected item is `EXTERNAL-ACCEPTANCE-ONLY` or explicitly NOT-RUN; no Windows or native-Qt result is claimed anywhere in this mission.