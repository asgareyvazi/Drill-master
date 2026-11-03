# M82–M100 Product Completion Report

Statuses: PASS / PARTIAL / BLOCKED / NOT IMPLEMENTED / NOT RUN / OWNER REVIEW REQUIRED.
Product label: **UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED**. No result here is a standards
qualification or field acceptance. Windows CI is not Windows desktop acceptance.

The live per-capability register is [`docs/engineering/PRODUCT_CAPABILITY_MATRIX.md`](../engineering/PRODUCT_CAPABILITY_MATRIX.md)
(section "M82–M100"). This report summarises the matrix and carries the evidence. It does not compete with it.

## A. Git

| Item | Value |
|---|---|
| Branch | `arena/72010272-drill-master` only; upstream `origin/arena/72010272-drill-master` |
| Start (M82 baseline, remote tip) | `0cd2a59c578ff2004124a92194fa6d8684e04fd1` (M70–M81 report) |
| **Final code SHA** | **`c776e8cd863b88623df0a8719cf497fbede93d73`** (every Python change of the programme; full suite, mutation and CI ran on it) |
| Report commit | the docs-only commit that adds this file and the M99 reconciliation; its SHA and CI are in the final reply, because a file cannot contain its own commit SHA |

**Baseline at the M82 start** (`git status --porcelain`/`--short`, `branch --show-current`, `rev-parse HEAD`,
`rev-parse @{u}`, `remote -v`, `ls-remote`, `stash list`, `worktree list`, `diff --check`, `log -1`): clean
tree, branch `arena/72010272-drill-master`, HEAD = upstream = remote tip `0cd2a59`, no stash, one worktree,
`diff --check` clean. The same command set was recorded at the final checkpoint (final reply).

Phase checkpoints (each pushed and confirmed with `git ls-remote` before the next phase):

| Phase | Commit |
|---|---|
| M83 selection lifecycle | `2090952785926784fc1108e8372170c2bd3327b6` |
| M85 survey references | `70991e49b9b5b9b909c2df2dffda0a3a8360ea9a` |
| M86 directional solver | `cf36425111df592a3dc0a82465036ca8217e61d9` |
| M87 W13 contracts | `ec8f0cf371da418b3194377fadddeac851f77cf4` |
| M88 history lineage | `177174ef3a67b89a2b8862fceda1f49f657b1384` |
| M89 architecture ↔ casing/cement | `3ac176f639e0b17bbd10d6874c75819877eabe10` |
| M90 engine qualification (+ inventory) | `7c666c8b4bdb93cd9a3bd959d14a41b5e359a139`, `388bc9d0739f05f67f0650a8ee5303dcfea42656` |
| M91 Operational Analysis | `2a8fb7c47712d732facfc0ebc0ec312470568102` |
| M92 Method Catalogue | `c0ccdb75f627953b91debf3ac9a4b408f2b847f5` |
| M84 DDR import identity / clean-up | `7f9b31b2fb9ba592bbee360fa51f58e255bccd6f` |
| M93 report provenance | `e665bf332f11500c6faad8061ea4ae54e9bfa582` |
| M94 journeys A–R | `3171752fa8779d74a388dba22e639e9b8b1e3920` |
| M95 UX responsiveness | `e2227cb70f00e7eaa0952f8a9fdd2ddf446c598e` |
| M96 persistence audit | `38d9266767b1c467b4b94d9fba248b56b36d8aa4` |
| M97/M98/M99 QA, owner procedure, docs | `c776e8cd863b88623df0a8719cf497fbede93d73` |

M84 ran after M92 because its remaining defects (file identity, parser clean-up) depended on the M83 context
work. The code diff `0cd2a59..c776e8c` covers 77 files (+6400/−237). New modules: `core/method_catalogue.py`,
`core/operational_analysis.py`, `core/report_provenance.py`, `dialogs/method_catalogue_dialog.py`,
`tabs/operational_analysis_panel.py`, `tools/quality/mutation_m83_m96.py`, `tools/quality/ux_responsiveness_m95.py`.

**Workspace recovery (non-destructive):** a sandbox reset during M96 moved the local ref back to
`4336ea357fc1ae28ccca228cdf7873697cc4cd84` and wiped `.venv`, the locally built Qt libraries, `/tmp` and the
upstream setting. Recovery used `git fetch`, a compare-and-swap `update-ref` to the pushed `e2227cb`,
`read-tree HEAD` and setting the upstream again. No commit was lost. No stash, `reset --hard`, `clean`,
force-push, merge, tag, release or history rewrite was used. `drill-Master`, branch protection and rulesets
were not touched.

## B. Per-phase results

| Phase | Status | Delivered (desktop path, persisted, scoped, tested) | Open gap |
|---|---|---|---|
| M82 forensic audit | PASS | Handler and capability inventory; starting defects verified against code; matrix section "M82–M100" | — |
| M83 selection lifecycle | PARTIAL | Clearing the selection empties every well-scoped tab (11 were stale); A→B switch leaves no identifiers of A; deletes clear the selection; three fixed defects (fake edits on view, W10 reset read as edit, W3c dead well-switch branch); 16 tests | Workers keep tab-local tokens; no company/project/rig/date/period signals; leak probe checks well identifiers only |
| M84 DDR authoring and import | PASS | File identity re-hashed immediately before the atomic save; parser results of unrun files released; truthful cancel; 4 new tests plus the pre-existing authoring/import suites | A running third-party parse is not interrupted (discarded, never committed; no thread killing, by design) |
| M85 survey references | PARTIAL | Declared azimuth reference (no silent "true"); explicit declination/convergence conversion as a new linked revision; station hash checked on every read; independent minimum-curvature benchmarks; 16 tests | Depth-datum and CRS transforms NOT IMPLEMENTED; plan files carry no declared reference |
| M86 directional | PASS (SCREENING for anti-collision) | Curve-hold solver from any tie-in direction, structured infeasibility, whole-arc inclination limit, independent goldens; anti-collision labelled "SCREENING — NO ISCWSA UNCERTAINTY — NOT APPROVED"; 17 tests | Multi-segment optimisation NOT IMPLEMENTED; no uncertainty model or separation factor |
| M87 W13 contracts | PARTIAL | Contract status for all 27 W13 leaves; 7 re-runnable contracts; case clone/export; re-runs are new linked cases; 16 tests | 20 calculators NOT_SUPPORTED (captured only, NOT REPRODUCIBLE with the reason shown) |
| M88 history | PARTIAL | 11 sources in one schema including survey and architecture revisions; recalculation from stored inputs as new linked records; lineage navigation; 8 tests | Legacy trajectory calculations and NOT_SUPPORTED calculators are captured only |
| M89 architecture, casing, cement | PARTIAL | Casing pins the architecture revision with per-value origin (derived/architecture/user/unknown); cement worksheet with segment geometry, caliper, open-hole excess and History; 10 tests | Cement stays a WORKSHEET; cement re-run NOT IMPLEMENTED |
| M90 engine qualification | PASS | Independent goldens per engine (hydraulics, mud, bit, MSE, casing, cement, T&D, well control, fishing, directional); fixed defects have regressions; 10 tests | 7.48 vs 7.48052 gal/ft³ documented deviation (OWNER REVIEW REQUIRED) |
| M91 Operational Analysis | PASS / PARTIAL | W12 → Operational analysis: footage, time-weighted ROP, NPT (time log and register side by side), activity, bit runs, per-currency cost, drill-down to W2, CSV/XLSX export; missing ≠ 0; 8 tests | MSE trend per well only; plan vs actual whole-well only |
| M92 Method Catalogue | PASS | Help → Method catalogue: 52 entries with ID, status, version, reference, licence, limits, approval and blocker; all NOT APPROVED; no approve action; 6 tests | Approvals are owner decisions |
| M93 reports and documents | PASS (provenance) / PARTIAL (exports) | Scope, sources, revisions, methods and the unsigned label on HTML/PDF (report PDFs are generated with QTextDocument, not PyMuPDF)/Excel/CSV, LTR and RTL; document index and search with manual well confirmation; no OCR; 11 tests | 16-sheet professional batch export not routed through provenance; RapidOCR OWNER REVIEW REQUIRED |
| M94 journeys A–R | PASS (offscreen) | Connected MainWindow journeys A–R through the UI path: A context, B DDR authoring, C DDR batch import, D survey, E plan from an inclined tie-in, F plan vs actual (SCREENING), G architecture and cement, H W13 case and re-run, I lineage, J operational analysis, K report provenance, L stale async, M well delete, N backup/restore, O offline, P language/RTL, Q method catalogue, R authorisation; 4 journey tests plus register | No in-app UI-language switcher (journey P covers Persian data and RTL output); offscreen, not a desktop |
| M95 UX audit | PARTIAL | Measured (offscreen Linux, ms): OA refresh 421 → 65; W10 refresh ≈360 → 144–148; two stalls fixed; 13 tests | Startup 1333 → 1349 unchanged within noise; no Windows measurement (owner procedure M98) |
| M96 persistence | PASS | Foreign keys on every connection (WAL, busy timeout 30 s); well delete no longer blocked by 6 legacy W13 tables (audited sweep); section delete unlinks procedures; history tables reject UPDATE, a replacing INSERT and a direct DELETE (triggers, additive); rollback leaves no partial delete; 39 tests | — |
| M97 qualification | PASS | §D | — |
| M98 owner procedure | PASS (document) / OWNER REVIEW REQUIRED (execution) | `packaging/WINDOWS_RELEASE_ACCEPTANCE.md` → "M82-M100 owner desktop acceptance procedure" | NOT EXECUTED — OWNER DESKTOP ACCEPTANCE REQUIRED |
| M99 reconciliation | PASS | Matrix (M97–M99, reconciled defect register), methods doc (M85–M96), workflows doc (14–17), `ENGINE_INVENTORY.md` (`--check` current), Windows doc, pointers from `PRODUCTION_READINESS.md` and `ENGINEERING_CAPABILITY_STATUS.md` to the single register | — |
| M100 adversarial audit and report | PASS | §F, this file | — |

Persistence and migrations: no table or column was added. The only schema change is additive guard triggers
(M96, `INSERT_GUARD_VERSION = 1`, `DELETE_GUARD_VERSION = 1`), installed idempotently on old databases.

## C. Methods

New or changed method versions in this programme (each stored with its results; a change is a new version,
never an edited constant):

| Method | Version | Status |
|---|---|---|
| Azimuth reference transform | M85 azimuth reference transform v1 (true = magnetic + declination, east +; true = grid + convergence) | NOT APPROVED; explicit values only, no lookup |
| Curve-hold target solver | M86 curve-hold target solver v2 | NOT APPROVED; goldens TD 1623.903201 m, J-profile VS 488.7133898 m |
| W13 contract registry | M87 calculator contracts v2 | 7 contracts / 20 NOT_SUPPORTED |
| Casing inputs from architecture | M89 casing inputs from architecture v1 (API TR 5C3 pipe-body subset) | NOT APPROVED |
| Cement annulus worksheet | M89 cement annulus worksheet v1 | WORKSHEET |
| Operational analysis | M91 operational analysis v1 | NOT APPROVED |
| Method catalogue | M92 method catalogue v1 | 52 entries, 0 approved |
| Report provenance | M93 report provenance v1 | — |

Limits and formulas: `docs/engineering/ENGINEERING_METHODS_AND_LIMITATIONS.md`. Anti-collision remains
centre-to-centre SCREENING with no uncertainty model. Unknown values stay unknown: datum, CRS, currency,
survey reference and material properties are never inferred. There is no online declination.

## D. Tests and CI

Environment for local evidence: Linux 6.1, 2 CPUs, Python 3.11.2, PySide6 6.8.1.1 with `QT_QPA_PLATFORM=offscreen`,
EGL/xkbcommon/dbus built locally from source, and a **stub** libGL (no GPU). These are offscreen results.

| Gate | Result on `c776e8cd863b88623df0a8719cf497fbede93d73` (local run unless marked CI) |
|---|---|
| Full suite (`python verify_release.py --coverage`, clean tree) | collected 4454: **4450 passed, 4 skipped**, 0 failed, 0 errors (1440 s) |
| Count vs M81 baseline (4272 passed + 4 skipped) | +178 = 178 items in the 14 new test files (M83 16, M84 4, M85 16, M86 17, M87 16, M88 8, M89 10, M90 10, M91 8, M92 6, M93 11, M94 4, M95 13, M96 39) + 1 M73 gap test (M97) − 1 M72 parametrized case (the "vertical tie-in" refusal, removed in M86 when inclined tie-ins became supported and replaced by positive goldens). 103 test functions added, 0 removed |
| Skips | Unchanged: `test_ddr_acceptance.py:33` ×2, `test_mineru_real_integration.py:26`, `test_packaging_smoke.py:218` (opt-in external acceptance, NOT RUN) |
| Coverage (branch+line, 240 tracked product files) | **66.29%**. *Corrected in M101:* the authoritative figure is the CI Python 3.12 job 125298732667 annotation, **62291/93969**. The 62289/93969 first written here came from the local Python 3.11 run and was not labelled as local; the 2-line difference comes from interpreter-dependent branches. Floor 45.50 unchanged; target 65 reached |
| Ruff on new and modified files | 0 new findings |
| Lint debt | 727 / ceiling 727 |
| Silent-exception scan | within ceiling |
| Privacy | 0 findings over 1309 files |
| Engine inventory | `--check` current |

**Mutation** (full selections; complete runs, not `--only` subsets):

| Suite | Mutants | Killed | Survived (non-equivalent) | Declared equivalent | Invalid |
|---|---|---|---|---|---|
| `mutation_m83_m96.py` (new) | 20 | 20 | 0 | 0 | 0 |
| `mutation_m70_m76.py` | 18 | 18 | 0 | 0 | 0 |
| `mutation_m61_m67.py` | 19 | 19 | 0 | 0 | 0 |
| `mutation_m52.py` | 70 | 69 | 0 | 1 (`W12-staged-paint-ignores-scope`, declared since M52; *M101 re-examination:* the equivalence proof missed an exception path, a killing scenario was added, and the mutant is now KILLED) | 0 |

The first `mutation_m83_m96` run gave 17 killed, 1 invalid (an anchor that matched twice) and 1 **survivor**:
`entry_status` could report an UNREADABLE history record as readable and no test failed. That was a real M73
gap. `test_entry_status_reports_records_whose_stored_data_cannot_be_read` now kills it. In `mutation_m52.py`,
two anchors went stale or ambiguous after M84/M95. They were re-anchored to the code that now holds the same
behaviour, and both are killed. No mutant was removed or weakened.

**Performance vs M80** (`tools/perf/m80_measure.py --cases 3000`, three runs, median ms; evidence, not a gate):
history full load 80.63 → 48.8–49.2; first page 12.04 → 10.2–10.9; survey save of 2000 stations
50.04 → 36.5–44.9; architecture save 1.08 → 0.83–1.29; build-hold solver ×1000 4.01 → 8.45–10.66. The solver is
slower because M86 replaced the vertical-only closed form with the general 3-D tie-in solver and a whole-arc
inclination check. Profiling puts it at about 9 µs per solve, and the UI runs one solve per user action.

**CI (exact full-SHA equality; cancelled runs are not counted):**

| Commit | Source release gate | Windows release validation |
|---|---|---|
| `c776e8cd863b88623df0a8719cf497fbede93d73` (final code) | success, run 41451853825 (jobs source 3.11 / 3.12 with coverage / 3.13: success) | success, run 41451853860 (job windows-release: success) |
| Report commit | final reply | final reply |

Warnings (*added in M101*): CI Python 3.12 logged 859 warnings, while the local Python 3.11 run logged 36. The M101 inventory (`verify_release.report_warnings`, now printed and annotated by every CI run) is in the M101–M120 report.

Earlier phase runs that a later push cancelled are not counted as evidence. For example, `38d9266`'s Windows
run 41447500349 was cancelled; its Source run 41447500289 succeeded.

## E. Owner register (open decisions; none taken by automation)

| Item | Decision needed |
|---|---|
| Windows desktop acceptance (M98 procedure, journeys A–R, M95 measurement) | Execute and record; NOT EXECUTED |
| Method approvals (52 catalogue entries) | Approve or reject per method; the application cannot approve |
| ISCWSA error model / welleng (Apache-2.0) | Adopt for uncertainty and separation factor, or keep SCREENING |
| pwptemp, torque_drag (LGPL-3.0) | Licence decision before any use |
| PyMuPDF (AGPL-3.0) | *Corrected in M101:* it is not excluded. It is a pre-existing mandatory dependency used by the PDF importers, document library and DDR PDF split. Keep it, make it optional or replace it: owner decision (evidence pack in M112). Report generation does not use it |
| OCR, local models, GPU (RapidOCR etc.) | Not adopted |
| Money model and currency conversion | Owner-gated; costs stay per currency |
| pcf/ppg constant (7.48 vs 7.48052) | Choose one; currently a documented deviation |
| Hydraulics reference, kill sheet | Reference selection |
| Depth datum / CRS support | Scope decision (NOT IMPLEMENTED) |
| Release, signing, tags, installer distribution, branch protection, history purge | Not performed |
| Field acceptance | NOT RUN |

## F. Adversarial audit and product status

Checks run against `0cd2a59..HEAD` and the working tree:

| # | Check | Result |
|---|---|---|
| 1 | Forbidden wording added to docs or UI | None (the one hit is "released" meaning freed parser memory) |
| 2 | PyMuPDF / fitz imported | None **added by this programme's diff** (`0cd2a59..HEAD`). *Scope corrected in M101:* PyMuPDF is a pre-existing mandatory dependency (`requirements.txt`, `requirements-lock.txt` 1.24.14, `pyproject.toml`). It is imported by `core/ddr_pdf_split.py`, `core/document_import.py`, `core/import_adapters/pdf_tables.py` and `core/document_library.py`. Its AGPL-3.0 owner decision is open (§E) |
| 3 | OCR, model, GPU or network client imported in product code | None |
| 4 | Binary, database, model or temporary report files added to git | None |
| 5 | Tags or releases created | None |
| 6 | CI workflows, coverage floor, lint or exception ceilings changed | No `.github/` change in the programme |
| 7 | Skips, xfails or import-skips added | None |
| 8 | Separation factor or uncertainty claimed | None; screening label present (`core/trajectory_compare.py`, catalogue) |
| 9 | "Approved"/"validated" labels on results | Only `APPROVED — <record>` from `OWNER_APPROVALS`, an empty read-only mapping (mutant `MC-approved-by-default` killed) |
| 10 | Exactly one M82–M100 report | This file |
| 11 | Competing capability registers | Older matrices are dated or marked historical; `PRODUCTION_READINESS.md` and `ENGINEERING_CAPABILITY_STATUS.md` now point to the single live matrix |
| 12 | Unsigned product label on exports and catalogue | Present (`core/report_provenance.py`, `core/calculation_cases.py`, `core/operational_analysis.py`, `core/method_catalogue.py`, `tabs/w11_Export.py`) |
| 13 | Online lookup for declination, CRS or methods | No URLs in the survey, solver, OA, catalogue or provenance modules |
| 14 | Unknown treated as zero (OA sums, cement volume, footage) | Killed mutants `OA-incomplete-sum-as-total`, `WA-excess-on-cased-hole`; footage decrease reads INVALID |
| 15 | Currency mixing | Per-currency rows only (M91 tests) |
| 16 | Immutability bypass (UPDATE, REPLACE, raw DELETE) | Refused at storage level (M96 tests; mutants `SG-replace-allowed`, `SG-single-delete-allowed` killed) |
| 17 | Stale async results applied after a context change | Refused (mutant `SM-stale-token-accepted` killed; journey L) |
| 18 | Import commits after cancel or after the file changed | Refused (mutant `Q-identity-not-rechecked` killed) |
| 19 | Test count change explained exactly | Yes (§D) |
| 20 | Mutation survivors hidden | No; the survivor and the invalid anchors are reported with their fixes (§D) |
| 21 | Windows desktop claims from offscreen runs | None; M95 and M94 are labelled offscreen; M98 is NOT EXECUTED |

**Product status:** integrated engineering product candidate, implemented and qualified within the documented
scope (matrix "M82–M100"). PARTIAL items: M83, M85, M87, M88, M89, M91 (MSE trend, plan vs actual),
M93 (batch exports) and M95. NOT IMPLEMENTED: depth datum, CRS, multi-segment optimisation, cement re-run,
interrupting a running third-party parse. Owner acceptance and release gates remain open.
**UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**
