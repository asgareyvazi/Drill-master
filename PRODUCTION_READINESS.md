# Production readiness and final import consistency gate

> **Canonical release-status authority.** This file separates repository verification from external acceptance. A static document cannot contain its own commit SHA; obtain the current exact identity with `git rev-parse HEAD` and count CI only when the workflow `head_sha` is identical.

## Current release status — M41 rheology/hydraulics certification

- **Repository and branch:** `asgareyvazi/Drill-master`, release branch `arena/01a0ec23-drill-master`; default/base branch `drill-Master`.
- **Required M41 baseline:** `2f49bc0817425711cb994e1d8605a672a5aed7dd` (M40 documentation follow-up). Baseline CI run [37461409652](https://github.com/asgareyvazi/Drill-master/actions/runs/37461409652) passed the source gate on Python 3.11/3.12/3.13, but it is not evidence for an M41 candidate.
- **M41 candidate verification:** BLOCKED until the M41 implementation/docs are committed, pushed, and a fresh exact-SHA Source release gate passes. Do not infer M41 status from the baseline run. For the candidate, require the workflow's full `head_sha` to equal `git rev-parse HEAD` on this branch.
- **Fann/Power Law contract:** M41 corrects the dimensional label: `K = 510·theta300/511^n` is reported in `cP·s^(n−1)` under the 300-rpm convention, with an explicit conversion to `(lbf/100 ft²)·s^n` before field pressure-loss and critical-velocity correlations. The legacy `power_law_k_equivalent_cp` output key remains for compatibility; it is not a plain-cP claim when `n != 1`. The M40 audit's earlier equivalent-cP wording is historical and is superseded by the M41 derivation.
- **Model scope:** Bingham and Power Law remain simplified screening correlations. Herschel–Bulkley does not have a validated yield-corrected solver here; pressure loss and ECD are `NOT_ASSESSED`, not a Power-Law-plus-yield surrogate. Transition correlations, empirical surface factor, geometry assumptions, and ECD remain explicitly limited as documented in the M41 audit.
- **M36/P6 and W5:** historical closure, `PROVENANCE_EXTERNAL_SOURCE_UNAVAILABLE`, 332/334 source-hash contexts, and the six open owner decisions are preserved; this M41 work does not adjudicate or rewrite them.
- **External acceptance:** Windows executable/installer, clean-machine install, real PDF/MinerU execution, production database, and operator/business acceptance remain NOT RUN unless separately evidenced below.
- **Release boundary:** source tests/static checks/package verification are repository evidence only; they do not establish external acceptance or standards compliance.

## Historical release status — M36 closure baseline / M37 hardening (as recorded 2026-10-04)

- **M37 starting baseline SHA:** `385cf63d833649bd41f932112828c8e2aa66328a` (M36 closure commit). This is a baseline, not a claim that later commits inherit its CI.
- **Exact-SHA Source release gate for that baseline:** run [37184840618](https://github.com/asgareyvazi/Drill-master/actions/runs/37184840618), Python 3.11/3.12/3.13 all PASS, including exact-source, locked dependencies, tests, and wheel verification. For any later candidate, inspect the [branch workflow runs](https://github.com/asgareyvazi/Drill-master/actions/workflows/ci.yml?query=branch%3Aarena%2F01a0ec23-drill-master) and require a successful run whose full `head_sha` equals current `git rev-parse HEAD`.
- **M36/P6:** 1,224 original records = 2 pre-P6 fixed + 1,222 adjudicated in batches 002–029 + 0 current OPEN. Structural and Git-history reconciliation pass; 332/334 source-hash contexts match.
- **W5 provenance:** `PROVENANCE_EXTERNAL_SOURCE_UNAVAILABLE` for `tabs/w5_Equipment_Widget.py`, SHA-256 `7cbe07214dbeb8cd3b8bb4668ec54040eec4e2e740e4e2188d24fd8c73758359`. Exact source and affected evidence remain unchanged; details are recorded in [`m36-master-ledger.json`](docs/audits/m36-evidence/m36-master-ledger.json).
- **Owner decisions:** `NEW-P6-007`, `-008`, `-015`, `-020`, `-023`, and `-024` remain open and separate from register arithmetic.
- **Real DDR XLSX:** PASS is recorded for the repository-tracked OEOC source in [`w16-integration-acceptance-2026-09-30.json`](docs/audits/m36-evidence/w16-integration-acceptance-2026-09-30.json); this is source-corpus integration evidence, not operator or production-database acceptance.
- **Real DDR PDF / external MinerU:** NOT RUN. **Windows bundle/installer and clean-machine install:** NOT RUN. **Production database and operator/business acceptance:** NOT RUN.
- **Engineering scope:** Casing is PARTIAL (not full API TR 5C3); Torque & Drag is PARTIAL / SCREENING; Anti-Collision is PARTIAL / SCREENING; production T&D and cement lab design are NOT_IMPLEMENTED. `EngineeringResult.scope` and current engine contracts remain authoritative.
- **Release scope:** repository source/tests/package verification only. A green source gate is not Windows, MinerU/PDF, production-database, or business acceptance.

The exact candidate SHA is deliberately resolved from Git rather than copied into
multiple documents. For a release decision, require `git status --porcelain` to
be empty and verify the successful Source release gate's `head_sha` equals
`git rev-parse HEAD` on this branch.

## Historical readiness records

The dated material below is retained for provenance. Its test counts, branch
names, CI claims, and “current” or “release posture” wording describe only the
recorded 2026 dates. They do not override the current release status above.


**Audit date:** 2026-09-08 — **re-verified:** 2026-09-09
(`docs/audits/2026-09-09/` holds the current forensic evidence and acceptance
table; the sections below retain the 2026-09-08 import-gate results).
**Release posture:** **NOT MERGE-READY until the required real Windows
acceptance is recorded.**

## Re-verification 2026-09-09 (summary)

* Full suite, Python 3.11, headless offscreen Qt: **808 passed, 0 failed,
  4 skipped (opt-in only)** — supersedes the 2026-09-08 count below.
* P0 defects fixed this session: undefined `CodeResolver` NameError silently
  dropped NPT contractors; dead tuple-key cache readers in
  `core/profile_import_engine.py` (workbook code catalog, embedded mud
  chemicals); two incompatible `ImportValidator` classes; broken `QAction`
  imports in `core/hierarchy_operations.py` and `core/toolbar_manager.py`
  (hidden for every recorded headless run by a DISPLAY-based skip); unsafe
  `object.__new__(QtDialog)` test construction.
* Well-centric acceptance scenario (one rig, three wells, sidetrack
  non-merge, DDR continuity, section/well consistency): automated in
  `tests/test_well_centric_acceptance.py`.
* Historical CI intent was not present at audit-start HEAD. The independent
  M27 patch supplies a workflow; remote CI remains **NOT VERIFIED**.
* Still NOT VERIFIED / BLOCKED: Windows GUI, installer, real MinerU/PDF,
  production database, Python 3.10/3.12/3.13 outside CI.

## Architecture gate

| Requirement | Status | Evidence |
| --- | --- | --- |
| One canonical Excel downstream path | PASS by source audit | `ExcelIntelligence` consumes `RawDocument`; no DB write in extractor |
| One canonical MinerU/PDF downstream path | PASS by source audit | `MinerUAdapter` -> `DocumentNormalizer` -> common IR/schema/review/save |
| No hidden ProfileImportEngine fallback | PASS | Smart Template hook disabled; direct profile DB method disabled |
| No DB legacy rescue after atomic failure | PASS | compatibility method delegates only to atomic saver |
| ReviewItem complete serialization/edit/save contract | PASS by source + real-workbook audit | `to_dict/from_dict`, normalized provenance/entity/type/mapping metadata, matrix restore, preview edit propagation; 0 missing core fields in the 2026-09-08 audit |
| AZNS-12 production Excel/PDF | **BLOCKED** | AZNS-12 production asset not present in repository/workspace. |
| Real Windows MinerU 3.4.5/PDF | **BLOCKED** | Windows executable/environment unavailable here |
| Python 3.12 acceptance | **BLOCKED** | Python 3.12 runtime not executed |

## Required real acceptance

Run on the user's actual Windows installation without reinstalling MinerU or
merging Python environments. Record:

- exact `mineru.exe` path and output of `mineru --version`;
- the separately managed Python executable and version;
- the exact command generated by `MinerUAdapter`;
- generated Markdown/JSON/assets and tables;
- canonical values, original/normalized units, review items, coordinates and
  source provenance;
- atomic database counts and UI-visible values;
- confirmation that a `Drilling Data` title cannot reach numeric conversion;
- explicit result for Python 3.12 only if that runtime was actually used.

The official command shape is `mineru -p INPUT -o OUTPUT -b BACKEND -m METHOD`;
the configured installation, not this document, is authoritative for paths.

## Test gate

The new `tests/test_ddr_acceptance.py` tests are marked `integration` and use
`DRILLMASTER_TEST_DDR_XLSX` and `DRILLMASTER_TEST_DDR_PDF`. They skip explicitly
when the relevant path is not supplied or when MinerU is unavailable. The
repository also contains atomicity, schema/alias/bounds, normalizer, unit,
optional-AI, MinerU failure-mode, security, packaging, and release tests.

A dependency-backed Python 3.11 environment at `/tmp/drill-venv` executed the
complete suite on 2026-09-08: 530 passed, 8 skipped, 0 failed/errors (538
collected), plus the real repository workbook audit. **Superseded on
2026-09-09 by the run recorded at the top of this file.** The base shell's
`pytest` command is not installed, and no Python 3.12 runtime, Windows
executable, real MinerU installation, AZNS-12 asset, or production DB was
executed. The pass count is therefore Linux/Python-3.11 evidence, not
Windows/Python-3.12 acceptance.

## Security and packaging

MinerU is subprocess-only with `shell=False`, argument-list invocation,
input/format checks, isolated output, timeout, captured output, and separate
process/output errors; failed/partial output is removed unless explicitly retained. PDF density units are not assumed. AI is disabled by default and advisory. No passwords,
MinerU environment, AI models, or generated real-document outputs belong in
Git.

The Windows PyInstaller/Inno Setup build remains defined by the existing
packaging scripts. This Linux environment cannot build/run the Windows PE
installer or perform clean-machine upgrade/uninstall checks; those are
BLOCKED until executed on Windows.

## Remaining defects/limitations

1. AZNS-12 production asset is unavailable: **AZNS-12 production asset not present in repository/workspace.**
2. Real MinerU/PDF execution, Windows GUI/Python 3.12/package acceptance, and
   production DB acceptance are not demonstrated here.
3. PDF native fallback (Camelot/PyMuPDF/OCR) is wired for PDF-only failure,
   carries weaker PDF-native provenance, and is not a MinerU PASS; it is allowed
   only when canonical template mapping can continue.
4. Smart Template and `ProfileImportEngine.analyze_and_extract()` remain
   compatibility code and should not be described as canonical importers.
5. Review items are exported in the import report but are not a dedicated ORM
   table; long-term audit retention depends on the report/export mechanism.
6. Existing informational legacy/static-audit findings remain outside this
   targeted fix.

## Merge gate

Merge readiness requires a clean working tree after commit, exact SHA, pushed
release branch (record its exact name and SHA), fresh dependency-backed test output,
package smoke output, and the Windows acceptance record. Until then the status
is **BLOCKED**.
