# Production readiness and final import consistency gate

> **Canonical release-status authority.** This file separates repository verification from external acceptance. A static document cannot contain its own commit SHA; obtain the current exact identity with `git rev-parse HEAD` and count CI only when the workflow `head_sha` is identical.

## Current release status — M42 / M42.1 Windows release engineering

- **Status:** M42 and the M42.1 closure work are implemented in the repository; the internal release decision is made only by exact-SHA CI. The M41 handoff below is the verified starting baseline; do not treat it as CI evidence for an M42 or M42.1 change.
- **Repository / fixed branch:** `asgareyvazi/Drill-master`, `arena/01a0ec23-drill-master`; default/base branch `drill-Master`. Resolve the current candidate with `git rev-parse HEAD`; accept CI only when its full `head_sha` equals that value and remote tip.
- **Verified M41 baseline:** `a482a91efad2aa982c54e9b3769ef6f698e2e9ef`; Source release gate [37598291126](https://github.com/asgareyvazi/Drill-master/actions/runs/37598291126) succeeded on Python 3.11/3.12/3.13 with exact matching `head_sha`. This is historical M41 baseline evidence only.
- **Windows automation (exists, not “being added”):** the dedicated **Windows release validation** workflow [`.github/workflows/windows-release-gate.yml`](.github/workflows/windows-release-gate.yml) runs on `windows-2022`: locked dependencies, Inno Setup 6.7.1, the Windows release regression suite, the PyInstaller portable bundle, `DrillMaster.exe --package-smoke`, installer compilation, artifact SHA-256 verification, and `acceptance-report.json` generation. The Linux Source release gate remains mandatory and separate. Such automation is not interactive installer acceptance.
- **M42.1 Windows regression forensics:** the credential-lifecycle and DDR-forensic Windows failures were one `WINDOWS_PORTABILITY_DEFECT` class: static tests read repository source (which contains UTF-8 Persian text) with `Path.read_text()` and no explicit `encoding`, so the runner's cp1252 default raised `UnicodeDecodeError`. The suite now states `encoding="utf-8"` and `tests/test_windows_release_gate_contract.py` plus `packaging/junit_report.py` guard the pattern and the annotation truncation limit. Product code already declared encodings; no security invariant was relaxed.
- **M42.1 packaging-stage evidence pipeline:** the first exact-SHA Windows run at `f047dc7` cleared the regression suite but its build step failed with no retrievable reason, because `release_dir` was published only on success (so the `always()` artifact upload captured nothing) and no annotation was emitted. The build step now publishes its evidence paths first, transcribes its own output, converts any thrown stage failure into one bounded, redacted `::error` annotation with the build-log tail, and builds with the interpreter the job provisioned (`-PythonExe`) instead of relying on the Windows `py` launcher. No artifact, no version claim and no gate outcome was weakened to obtain this.
- **Machine-readable closure checkpoint:** [`docs/audits/m42-1-release-closure.json`](docs/audits/m42-1-release-closure.json) records the gate contract and the deliberately uncommitted run-ID evidence rule.
- **Current engineering boundaries (preserved):** Bingham/Power Law hydraulics, ECD, surge/swab, and empirical surface factor are screening; Herschel–Bulkley pressure loss/ECD remain `NOT_ASSESSED`; well control is a deterministic calculation kit without standards-compliance claim; casing is PARTIAL (not full API TR 5C3); torque & drag and anti-collision are PARTIAL/SCREENING; production T&D and cement laboratory design are NOT_IMPLEMENTED.
- **M36/P6/W5:** historical closure, `PROVENANCE_EXTERNAL_SOURCE_UNAVAILABLE`, 332/334 source-hash contexts, and six open owner decisions remain preserved and are not adjudicated by M42.
- **External acceptance remains separate:** clean Windows machine, interactive install/upgrade/uninstall, actual DDR PDF and MinerU, production database, field validation, and operator/business sign-off are NOT RUN unless separately evidenced.
- **Release decision:** until the current candidate source and the applicable Windows workflow runs pass on the same exact final SHA, M42.1 is **BLOCKED**. Once those automated repository gates pass on the final SHA, the posture is **RELEASE-ENGINEERING PASS WITH EXPLICIT EXTERNAL ACCEPTANCE PENDING** — not “production certified”. This file never records a gate result for its own commit; the run IDs live in the mission report and in the generated `acceptance-report.json`.

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
