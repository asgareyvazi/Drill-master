# M70–M81 Product Completion, Engineering Integrity, Integration and Final Acceptance Report

Statuses used: PASS / PARTIAL / FAIL / BLOCKED / NOT IMPLEMENTED / NOT RUN / OWNER REVIEW REQUIRED.
Release status: **UNSIGNED, NOT RELEASE-APPROVED**. Nothing here is API-, ISCWSA- or field-qualified.

## 1. SHAs

| Item | Value |
|---|---|
| Start (remote tip) | `320fd44252bad760aff2985d66db70903d533eae` (M61–M69 docs); preceding code `d3a64f3` |
| M70 pushed tip | `5b3a2c2cb933e7e8d216aaa1d589f81f926c9f0d` |
| Code + canonical docs tip | `05920d028832b19009b28871f3adb81b65649cc3` |
| Mutation tooling | `5a464faaa1f984ba96b717e990312641407c1b15` |
| Final code tip | `c9e13e4c28ef3499702c8a9afd052f5a426d6f9d` (CI job limit only; Python identical to `5a464fa`) |
| Report commit | the commit that adds this file (docs only); its SHA and CI are in the final reply, because a file cannot contain its own commit SHA |

## 2. Branch and remote

`arena/72010272-drill-master` only; upstream `origin/arena/72010272-drill-master` (local config). No merge, tag,
release, signing, force-push or history rewrite. `main`, `drill-Master`, branch protection and rulesets untouched.

Workspace recovery (non-destructive): a sandbox reset during M71 discarded `.venv`, `/tmp` and four unpushed
local commits (`3bc2f02`, `d8bec15`, `a9a1781`, `d359ff9`; their working-tree content survived). Recovery used
`git fetch`, a temporary index to verify the tree, a compare-and-swap `update-ref` of the local branch to the
pushed `5b3a2c2`, and `read-tree HEAD`; the work was re-committed as `a26da52`…`446bdcc` (same content, new SHAs).
No stash, `reset --hard` or `clean`.

## 3. Commits and files

17 commits after `320fd44`: M70 `eb0839e`, `63dc2f4`, `9cc4306`, `0f5c51a`, `54d0ab4`, `5b3a2c2`; M71 `a26da52`;
M72 `8db95b0`, `dd1ed11`; M73 `6fa60d1`; M74 `446bdcc`; M75 `8caa897`; M76 `1b26712`; M78 `ded6a5d`;
M79 `d134b5e`; M80 `80a379c`; docs `05920d0`; mutation tooling `5a464fa`; CI job limit `c9e13e4`.
56 files changed (26 added, 30 modified) up to `c9e13e4`; +6001 / −419 lines up to `5a464fa`.

New runtime modules: `core/storage_guards.py`, `core/ddr_import_pipeline.py`, `core/survey_revisions.py`,
`core/calculator_contracts.py`, `core/well_architecture.py`, `core/specialist_methods.py`,
`tabs/survey_revision_panel.py`, `tabs/well_architecture_panel.py`. Tools: `tools/quality/engine_inventory.py`,
`tools/quality/mutation_m70_m76.py`, `tools/perf/m80_measure.py`.

## 4. Phase results

| Phase | Status | Basis |
|---|---|---|
| M70 integrity | PARTIAL | 70.1–70.6 PASS (storage triggers + service checks, whole-result verification, lineage table, well delete, plan comparison, queue rules); 70.7 selection audit PARTIAL (see §17) |
| M71 DDR background pipeline | PARTIAL | Preparation in a worker with DTOs; cancel, safe close, late-result guard, column report, no-text-layer pages reported. Cancellation is cooperative between steps (a running parse step finishes) |
| M72 surveys, tie-in, solver, plan vs actual | PARTIAL | Immutable survey revisions in the UI; plans pin the exact revision; 3D target checks. No azimuth/datum conversion; solver closed form with vertical tie-in only |
| M73 calculator contracts, history | PARTIAL | Contract framework, separate readable/comparable/reproducible statuses, unit-safe compare, DB-side filters and paging. One contract (Quick Calc); older cases NOT_REPRODUCIBLE |
| M74 well architecture | PARTIAL | Revisions, validation, schematic from records, cement annulus worksheet pinned to the revision. Casing calculator does not record the architecture revision |
| M75 engine inventory | PASS | Generated inventory checked by a test; 18 formula/guard mutants killed |
| M76 engineering labels | PARTIAL | Kill sheet TRAINING AID notice; cement worksheet per architecture revision (no contract, NOT REPRODUCIBLE); no casing/T&D method changes |
| M77 operations analysis | PARTIAL (no code) | Existing W12 KPI evidence and Home dashboard reused; no new W12/W16 drill-down or shared time basis |
| M78 workflows A–F | PASS for the tested chains | Automated, offscreen; report page breaks and status rows added |
| M79 specialist registry | PARTIAL / OWNER REVIEW REQUIRED | Registry and six-criteria rule; no new method met all six; not shown in the UI |
| M80 desktop / recovery / offline | PARTIAL | Restore keeps revisions and guards; offline scan; measured timings; manual checklist written, NOT EXECUTED |
| M81 qualification | PASS for the gates in §10–§15 | Desktop and field acceptance not performed |

## 5. Workflows (M78, automated, offscreen Qt with real widgets on synthetic DBs)

| ID | Chain | Test | Status |
|---|---|---|---|
| A | survey revision → tied plan → compare | `tests/test_m72_survey_ui.py` | PASS |
| B | W13 contract case → History → verify → saved recalculation with lineage → report | `tests/test_m78_workflows.py` | PASS |
| C | architecture revision → cement worksheet → History | `tests/test_m78_workflows.py` | PASS |
| D | DDR files prepared in the background, reviewed, saved | `tests/test_m71_ddr_background.py` | PASS |
| E | well delete with every new record type | `tests/test_m78_workflows.py`, `tests/test_m70_integrity.py` | PASS |
| F | report quality: HTML escaping, Unicode, page breaks, statuses | `tests/test_m78_workflows.py` | PASS |

User-facing steps: `docs/engineering/DRILLMASTER_USER_WORKFLOWS.md` §12–13.

## 6. Database and migrations

Additive only; old databases upgrade in place (fresh and upgraded DBs tested in M70/M72/M74).
New tables: `calculation_source_links`, `survey_revisions`, `well_architecture_revisions`; unique
`uq_survey_revision` and `uq_well_architecture_revision` (well, revision). Ten indexes added through
`INDEX_PLAN` (well scope, hierarchy, lineage). Storage triggers (`core/storage_guards.py`, `GUARD_VERSION = 1`):
immutability for calculation cases, source links, plan revisions, survey revisions and architecture
revisions, plus the plan status transition trigger (draft→approved/archived, approved→archived, archived
final). `ON DELETE` cascades remove a deleted well's records; `SET NULL` on references is allowed by the
triggers only when the referenced row is gone. Money migration not touched (owner-gated).

## 7. Methods and versions

| Area | Version |
|---|---|
| Survey revisions | `M72 survey revision v1` |
| Plan designer | `M72 plan designer v3` (v2 plans verify as METHOD CHANGED, identical stations) |
| Build-hold solver | `M72 build-hold target solver v1` |
| Calculator contracts | `M73 calculator contracts v1`; Quick Calc method `M73 pipe capacity v1` |
| Well architecture | `M74 well architecture v1` |
| Queue | `QUEUE_VERSION = 2` |

Formulas, limits and refusals: `docs/engineering/ENGINEERING_METHODS_AND_LIMITATIONS.md` (M72–M79 sections).

## 8. Benchmarks and measurements

Independent references (hand-derived, not produced by the code under test): build-hold golden (KOP 500 m,
3°/30 m, target N −300 E 300 TVD 1400 m → 30.0° at 135.0°, TD 1623.903201 m, miss 3e-13 m); J-profile TD
1623.9032011 m, VS 488.7133898 m; Teale MSE 127997.67 psi; bit ΔP 920.98 psi; capacity 0.017762 bbl/ft;
cement annulus (Dh² − Dp²)/1029.4 × 3.28084 × L.

M80 measurements (`tools/perf/m80_measure.py`, synthetic, 3000 cases, this 2-CPU Linux sandbox, Python 3.11;
evidence, not gates):

| Path | Median ms | Max ms |
|---|---|---|
| History full load | 80.63 | 94.07 |
| History count + first page (200) | 12.04 | 34.65 |
| Survey revision save, 2000 stations | 50.04 | 66.95 |
| Architecture revision save | 1.08 | 2.96 |
| Build-hold solver × 1000 | 4.01 | 4.21 |

UI responsiveness on a Windows desktop was not measured.

## 9. Authorization and integrity

Plan lifecycle and revision writes run inside `OperationScope` permissions; invalid transitions are refused
in the service and by the trigger, and audited (`PLAN_STATUS_REJECTED`). Revisions are verified by recomputing
results against the stored SHA-256; parents must be the latest revision of the same lineage, well and
wellbore. Survey pins are re-checked on plan save (well, wellbore, the pinned SHA-256 against the revision's
stored SHA-256, station). Architecture components are re-hashed on read; survey stations are not re-hashed on
read (their row is protected by the storage trigger only). Recalculations are saved as new cases linked by `calculation_source_links`; nothing is
overwritten. Backup/restore preserves revisions and their triggers (`tests/test_m80_recovery_offline.py`).

## 10. Tests

| Run | Result |
|---|---|
| Full suite at `446bdcc` (M74 tip), local Linux, offscreen | 4257 passed, 4 skipped, 0 failed (18m56s) |
| Changed-area suite at `05920d0` (M74–M80, W13, history, release gates) | 272 passed |
| Full suite at `5a464fa` (Python identical to the final code `c9e13e4`), clean clone, local | 4272 passed, 4 skipped, 0 failed (19m16s) |
| CI at `05920d0`, `5a464fa`, `c9e13e4` | full suite on Python 3.11/3.12/3.13 and Windows (§15) |

Count changes from the M61–M69 baseline (4089 passed + 4 skipped): M70 +88, M71 +11, M72 +35, M73 +7,
M74 +27, M75 +4, M76 +2, M78 +4, M79 +3, M80 +2 = +183. Expected skips (unchanged): `test_ddr_acceptance.py:33`
×2, `test_mineru_real_integration.py:26`, `test_packaging_smoke.py:218`. No test was skipped, weakened or removed.

## 11. Coverage

CI coverage leg (Python 3.12, branch+line, coverage 7.16.2) at `05920d0`: **63.80%** over 235 tracked files
(58587/91836); floor 45.50% kept (not raised in this programme). Final code `c9e13e4` (job 125130010012): **63.80%** (58590/91836, 235 files).

## 12. Mutation

| Set | Result |
|---|---|
| `tools/quality/mutation_m70_m76.py` (18: hydraulics constants, Fann PV, Teale MSE, storage guard, solver infeasibility and tie-in, survey SHA, contracts, unit mismatch, architecture rules) | first run 15 killed, 1 survived, 2 invalid; final 18/18 killed |
| `tools/quality/mutation_m61_m67.py` (19, regression) | first run 13 killed, 6 invalid; final 19/19 killed |

Honest account: the two capacity mutants were invalid (pattern also matched the `* length_ft` variant; anchored
to the line end). `HY-fann-pv` survived because only the golden files were selected; the existing assertion in
`tests/test_hydraulics_m40_regressions.py` (PV 20 cP from 45/25) kills it once selected; the independent golden
files themselves do not cover Fann PV. Six M61–M67 mutants no longer matched after the M70–M73 refactors and
were re-pointed at the same guards in their new location (`_mark_twin`, the run-loop cancel check,
`_next_revision`, `PLAN_STATUS_TRANSITIONS`, the re-run `parent_id`, the history well filter). No mutant was
declared equivalent; no hard mutant was changed.

## 13. Ruff and lint

Ruff on all 50 Python files new or modified since `320fd44`: every new file clean; no modified file has more
findings than at `320fd44` (legacy findings remain in `core/database.py` and W13). Repository lint debt 727,
ceiling 727 (not raised). Silent-exception ceiling check rc 0.

## 14. Privacy and exceptions

Privacy gate: 0 findings (1287 files). Synthetic fixtures only; no real DDR or history file opened; no names,
coordinates, serials or money values added. No new PNG. No network import in the new modules (AST check).
No OCR, model, GPU or cloud dependency added; no new third-party code copied.

## 15. CI (exact full-SHA equality)

| SHA | Workflow | Run | Jobs | Result |
|---|---|---|---|---|
| `5b3a2c2…` | Source release gate | 41309498017 | 3 | success |
| `5b3a2c2…` | Windows release validation | 41309497961 | 1 | success |
| `05920d028832b19009b28871f3adb81b65649cc3` | Source release gate | 41394177504 | source (3.11) 125111836055, (3.12) 125111835883, (3.13) 125111835958 | success |
| `05920d028832b19009b28871f3adb81b65649cc3` | Windows release validation | 41394177398 | windows-release 125111835672 | success |
| `5a464faaa1f984ba96b717e990312641407c1b15` | Source release gate | 41397350797 | (3.11) 125121435025 success, (3.13) 125121435276 success, (3.12) 125121435296 **cancelled: exceeded the 25-minute job limit** | not green |
| `5a464faaa1f984ba96b717e990312641407c1b15` | Windows release validation | 41397350865 | windows-release 125121428630 | success |
| `c9e13e4c28ef3499702c8a9afd052f5a426d6f9d` | Source release gate | 41400144183 | source (3.11) 125130010017, (3.12) 125130010012 (22m33s), (3.13) 125130009754 | success |
| `c9e13e4c28ef3499702c8a9afd052f5a426d6f9d` | Windows release validation | 41400144135 | windows-release 125130009810 | success |

The `5a464fa` coverage leg was stopped by the workflow time limit while running tests (the same leg took
22m12s at `05920d0`); it is not counted as a pass. `c9e13e4` raises the source job limit from 25 to 40 minutes
(the Windows gate already allows 60); no test, assertion, floor or ceiling changed.
Branch `arena/72010272-drill-master`, event `push`. The Windows job is not desktop acceptance.

## 16. Cleanliness

At the report commit: local HEAD equals the remote; upstream set; no untracked, unpushed or stashed work; no
extra worktree. Temporary clones and logs are outside the repository (`/tmp`). Mutation runs restored every
source file (verified with `git status`).

## 17. Limitations

- M70.7: tabs do not uniformly guard `on_well_changed(None)`; `on_selection_cleared` is overridden only in W4,
  W6 and W12; `wellbore_changed` is used only by W12 and W3b; there is no company/project/date selection state.
- M71: cancellation is cooperative; no OCR (pages without a text layer are reported, not read).
- M72: no azimuth (grid/true/magnetic) or datum conversion; the solver handles a vertical tie-in only; target
  and anti-collision results are SCREENING.
- M73: only Quick Calc has a contract; cases saved before M73 are NOT_REPRODUCIBLE.
- M74/M76: the cement annulus is a WORKSHEET (nominal sizes, no caliper or excess) without a contract; clearance is
  judged only when the hole size is known; the casing calculator does not record the architecture revision.
- M76: casing stays the TR 5C3 pipe-body subset; T&D stays soft-string SCREENING; kill sheet stays TRAINING AID.
- M77: no new KPIs, chart drill-down or common time basis on W12/W16.
- M79: registry not visible in the UI.
- M80: timings are from a Linux sandbox; Windows desktop behaviour was not observed.

## 18. Owner decisions required

| Item | Decision needed |
|---|---|
| ISCWSA error model (welleng) | licence acceptance and engineering approval before implementation |
| pwptemp temperature model | LGPL-3.0 acceptance |
| PyMuPDF | AGPL acceptance |
| OCR / models / embeddings / ML datasets / GPU | any adoption |
| Well-control acceptance | whether the kill sheet may leave TRAINING AID |
| Windows desktop and field acceptance | execute `packaging/WINDOWS_RELEASE_ACCEPTANCE.md` incl. M80-01…12 |
| Release, tag, signing; branch protection; history purge; money migration | unchanged, not touched |

## 19. Windows acceptance

Checklist "M70-M81 desktop feature acceptance (manual; NOT EXECUTED)", rows M80-01…M80-12, added to
`packaging/WINDOWS_RELEASE_ACCEPTANCE.md`. **NOT RUN.** Windows CI passing is not desktop acceptance.

## 20. Canonical documents updated

`docs/engineering/ENGINEERING_METHODS_AND_LIMITATIONS.md` (M72–M79), `PRODUCT_CAPABILITY_MATRIX.md`
(M70–M80 table), `DRILLMASTER_USER_WORKFLOWS.md` (§12–13), generated `ENGINE_INVENTORY.md`. The report commit
corrects two survey statements in the methods document pushed in `05920d0` (unit/reference defaults; the stored
SHA-256 covers the stations, not the result).

## 21. Acceptance summary

A feature counts as PASS only when usable from the desktop UI, persisted, traceable, error-handled and
tested. By that rule: immutable plan/case/survey/architecture revisions, lineage, History statuses, survey
tie-in and architecture revisions are usable and tested offscreen; none has been accepted on a Windows desktop.

## 22. Release status

Feature-complete engineering product **candidate** with owner gates open. **UNSIGNED, NOT RELEASE-APPROVED**;
no EXE, installer, tag or release produced.
