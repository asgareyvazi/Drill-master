# M141–M170 — Integrated Engineering, DDR Repair, Product Consolidation & Advanced Completion

**UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**

Branch `arena/72010272-drill-master`. Baseline code `20dfe56`, baseline report `ba4e0a8`.

| Commit | Content |
|---|---|
| `d5766be` | M147–M153: continuation contract, persisted review queue, safe partial import, review workspace, CONTEXT_BLOCKED (hidden tabs) |
| `c20f5cd` | M157–M160: tubular reference library, snapshots, search dialog, workbook warnings; mutation catalog |
| `9b4025d` | M153 second root cause (Daily Report own navigation), M169 journey, index plan, Windows gate |
| report | the commit adding this file (its own CI cannot be listed inside it) |

All numbers were measured in this mission unless marked *(baseline)*. Synthetic data only. The real DDR workbook
named by the user was never opened.

---

## A. Git baseline and final state

### Baseline

| Check | Result |
|---|---|
| Branch ref at start | `4336ea3`: the parent session's tip, not this session's work, with the environment missing (a sandbox reset) |
| Recovery | `git fetch`; CAS `update-ref refs/heads/arena/72010272-drill-master ba4e0a8 4336ea3`; `read-tree HEAD`; `branch --set-upstream-to`. No `reset --hard`, no `clean`, nothing discarded |
| HEAD / `@{u}` | `ba4e0a8` / `ba4e0a8` |
| `status --porcelain=v2 --branch` | clean, `branch.ab +0 -0` |
| `stash list` | empty |
| `worktree list --porcelain` | one worktree |
| `diff --check` | clean |
| `ls-remote origin` | no `refs/heads/main`; `refs/heads/drill-Master` = `e3fa42a3257e` = remote `HEAD` (untouched) |
| `log --oneline --decorate` (top) | `ba4e0a8` → `20dfe56` → `2b4e0d6` → `5c0c0c8` → `74c81d6` → `456a5b9` → `28a1fbf` → `15db396` → `a6e506a` → `443a1e3` |

### Second sandbox reset (mid-mission)

After `c20f5cd` was pushed the sandbox reset again. The branch ref moved back to `4336ea3`, and the virtualenv,
the locally built Qt libraries and `/tmp` were wiped. The working tree kept every file.

Recovery:
- CAS `update-ref … c20f5cd 4336ea3`, then `read-tree HEAD` and upstream reset. After that only the three
  uncommitted files of the moment remained modified.
- Environment rebuilt: venv from `requirements-lock.txt` plus the CI tool pins; libglvnd 1.7.0, dbus 1.14.10,
  expat 2.6.4, byacc and xkbcommon 1.7.0 from source.

Lost and redone: the report draft in `/tmp` and an interrupted full-suite log.

### Final state

Measured after the last code commit and before the report commit:

| Check | Result |
|---|---|
| HEAD / `@{u}` | `9b4025dd000582bdc015d416a1a158fd7e16e41d` / same (`branch.ab +0 -0`, after `git fetch`) |
| `status --porcelain=v2` | clean |
| `stash list` | empty |
| `worktree list --porcelain` | one worktree |
| `diff --check` | clean |
| `ls-remote origin` | `refs/heads/arena/72010272-drill-master` = `9b4025d`; no `refs/heads/main`; `refs/heads/drill-Master` = `e3fa42a3257e981d9bdf9d012c97919e3352a53a` = remote `HEAD` (untouched) |
| History | linear on top of `ba4e0a8`: `d5766be` → `c20f5cd` → `9b4025d`. No force-push, no tags, no releases |

The report commit is pushed the same way and verified with `git fetch` plus `ls-remote` (stated in the reply,
because a file cannot contain its own SHA).

---

## B. Per-phase results

States: PASS / PARTIAL / OPEN / BLOCKED / OWNER REVIEW REQUIRED / NOT IMPLEMENTED / NOT RUN.

| Phase | State | Evidence |
|---|---|---|
| M141 Baseline evidence | PASS | section A |
| M142 Consolidated register | PASS | section H |
| M143 D51 diagnostics | **OPEN** | section G. No reproduction and no new frame. No timeout raised, no retry added |
| M144 Preserve D28, D40, D46 residual, D52–D60 | PASS | their tests are in the full suite; D60 mutants are in the complete M121–M140 run |
| M145 D6 lineage | PARTIAL (unchanged) | no new evidence; the M123 audited repair stands |
| M146 D11 CRS | NOT ASSESSED / OWNER REVIEW REQUIRED | no CRS is guessed |
| M147 Reproduce the 34 pending reviews | PASS | C.1 |
| M148 One continuation contract | PASS | C.2 |
| M149 States, persistent ids, attach operation | PASS | C.3 |
| M150 Safe partial import | PASS | C.3; journey steps 4–7 |
| M151 Review workspace | PARTIAL | filters, multi-select, attach / reject / ignore, parent visible. Deferred *scalar* corrections need a re-import |
| M152 Same semantics on every route | PARTIAL | XLSX profile, generic Excel, native PDF / MinerU profile rule and smart template proven. MinerU leaves "Activity", "Description", "Operation" and "Details" headers unmapped (coverage limit) |
| M153 CONTEXT_BLOCKED | PASS | C.5: two root causes, both reproduced in the real window; guard kept |
| M154 Real-Qt plus DB regression programme | PASS | `test_m147_m152` (34), `test_m153` (10), `test_m157_m160` (20), journey (1 × 20 steps) |
| M155 Forensic map of well-path UIs | PASS | section D |
| M156 One canonical workflow | PARTIAL | canonical path declared. The legacy "Trajectory Plot" tab stays because it has plot save and data export the viewer lacks |
| M157 Typed versioned pipe reference DB | PASS | E.1 |
| M158 Populate from licensed sources | **BLOCKED (source rights)** | E.2. Nothing invented, nothing shipped |
| M159 Search UI, module integration, snapshots | PARTIAL | dialog, immutable snapshots and drift report done. NOT yet integrated into Architecture, Volumes, Hydraulics, Weight, Casing or T&D |
| M160 DrillPipe / Data Validation warnings | PASS | E.3 |
| M161 External audit | PARTIAL | 19 named repositories pinned at exact SHAs (section F). The earlier "50-source" list was NOT re-audited |
| M162 Adoption | PASS (nothing adopted) | no candidate passed qualification; no new dependency |
| M163 W13 registry | PASS (unchanged) | 27 leaves: CONTRACT 9, SCREENING 10, WORKSHEET 4, TRAINING AID 1, REFERENCE-ONLY 1, NOT_SUPPORTED 2 |
| M164 Close real gaps without relabelling | PARTIAL | the gaps closed are M147–M160; no W13 leaf relabelled |
| M165 Pipe-reference consistency | OPEN | follows the M159 integration |
| M166 MATCH / DIFFERENT / NOT_REPRODUCIBLE / UNREADABLE | PASS (unchanged) | 7.48 vs 7.48052 not changed globally (owner decision) |
| M167 Dependency and licence gates | PASS | 26 locked, 168 imports, findings 0, FAIL 0; no new dependency |
| M168 Security honesty | PASS (unchanged) | no new security claim |
| M169 Layered tests, journey, mutants, gates | **PASS** | section G |
| M170 Adversarial audit, push, CI | **PASS** (code SHA). Report SHA CI: see the reply | sections A and G |

### Files

| Phase | Files |
|---|---|
| M147–M152 | **New:** `core/ddr_continuation.py`, `core/import_review_queue.py`, `dialogs/import_review_dialog.py`.<br>**Changed:** `core/import_quality.py`, `core/ddr_import_pipeline.py` (`PIPELINE_VERSION` 2), `core/ddr_import_service.py`, `core/database.py` (`ImportReviewItem`), `core/authorization.py`, `core/schema_indexes.py`, `core/profile_import_engine.py`, `dialogs/excel_import_dialog.py`, `dialogs/smart_template_dialog.py`, `main_window.py`.<br>**Tests:** `tests/test_m147_m152_ddr_continuation.py` |
| M153 | **Changed:** `core/base_tab.py`, `core/save_outcome.py`, `core/managers.py`, `tabs/w2_Daily_Report.py`.<br>**Tests:** `tests/test_m153_context_blocked_autosave.py` |
| M157–M159 | **New:** `core/engineering/tubular_reference.py`, `dialogs/tubular_reference_dialog.py`.<br>**Changed:** `core/database.py` (`TubularReferenceSet`, `TubularReferenceItem`), `core/authorization.py`, `core/schema_indexes.py`, `main_window.py`.<br>**Tests:** `tests/test_m157_m160_tubular_reference.py` |
| M160 | **New:** `core/workbook_io.py`.<br>**Changed:** `core/ddr_import_service.py`, `core/profile_import_engine.py`, `core/import_router.py`, `core/excel_normalizer.py`, `core/engineering/drill_pipe_import.py`, `dialogs/smart_template_dialog.py`, `tabs/w13_Engineering_Calculator.py` |
| M169/M170 | **New:** `tools/quality/mutation_m141_m170.py`, `tests/test_m169_end_to_end_journey.py`.<br>**Changed:** `.github/workflows/windows-release-gate.yml`, `tests/test_windows_release_gate_contract.py`, `docs/engineering/dependency_audit.json`, `core/schema_indexes.py` |

---

## C. DDR import

### C.1 Root cause of "Resolve every review row before import (34 pending)" (M147)

1. `validate_logs` added a `time_log.continuation` review for **every** row that had a description but no
   times. It carried confidence 0.8, decision REVIEW and the false text "will be merged".
   - 0.8 sits between auto-accept (≥ 0.95) and auto-reject (< 0.70), so every such row was left for the user.
   - `_confirm` then blocked the import until all of them were resolved.
2. Accepting one merged nothing. `apply_review_decisions` routed it to `time_logs_24h` and set a field
   `record["continuation"]` on an unrelated record.
3. The profile route merged narrative rows silently, without lineage, and invented a `"PLN"` status.
4. `_save_time_logs` turned time-less rows into `invalid_time_range` reviews that existed only in the audit JSON.
5. **Generating routes:** all of them. Generic Excel keeps narrative rows as time-less records (fixture rows 25,
   28 and 33); the profile, MinerU, native-PDF and smart-template routes produce them too.

The synthetic golden workbook alone yields 35 review rows: 4 continuations and 31 scalar reviews (well
latitude/longitude, KOP, water depth, report notes, …). The user's count of 34 is consistent with this mechanism.

### C.2 Contract (M148, `ddr-continuation-v1`)

A narrative row is attached to the activity above it **only** when all of these hold:
- the profile allows continuations;
- the row is not a header, footer or total line;
- the anchor row is timed;
- both rows have the same collection, file, sheet, table and page;
- both source row numbers exist, are integers and strictly increase.

The text is attached with its line break and `_continuations` lineage. Nothing else is ever invented: no time,
duration, code, depth or parent.

- **Review id:** `cont-` + SHA-256 of (contract, location, index, text).
- ACCEPT on a continuation is refused.
- A decision payload whose index contradicts its id is not applied.

### C.3 States and the queue (M149/M150)

**States:** ACCEPTED, REJECTED, IGNORED, SAFELY_ATTACHED_CONTINUATION, DEFERRED_UNRESOLVED, VALIDATION_ERROR.

The queue (`import_review_items`) is unique on report and review id, cascades with its report, and is written in
the same transaction as the report.

Partial import:
- It needs explicit consent: "Import verified records and retain N unresolved item(s) for review".
- The summary states what was saved and what was retained. In the journey: 1 attached, 34 retained, all 34
  persisted.
- A deferred proposal never becomes canonical.

Queue decisions:
- Every decision is audited (`ddr_review_decision`).
- A decided item is never decided again (`ValueError`, "nothing was changed").
- A foreign well is refused.

### C.4 Evidence (M152)

**Golden synthetic workbook, real generic route:**
- 4 continuations attached: 3 × 24-hour and 1 morning, all keeping their line break.
- 7 time logs.
- Source SHA-256 unchanged.

**Other routes:** the profile and MinerU / native-PDF routes follow the profile rule; the smart template keeps
provenance.

**Limit:** four MinerU description headers are unmapped.

**Observation (pre-existing, not changed):** the import files a report under the well identified *inside the
workbook*, not necessarily the well that was selected.

### C.5 CONTEXT_BLOCKED (M153): two root causes

**Root cause 1: hidden tabs.**
- `MainWindow` arms a 5-minute auto-save timer for every save-capable tab, hidden ones included.
- A selection change, including an import's `select_full_context`, reaches a hidden tab as a pending context. It
  is loaded only on `showEvent`.
- Every tick then hit the guard and logged "Auto-save: CONTEXT_BLOCKED: 0 save operation(s)…", although nothing
  had been edited.
- Reproduced in the real window for Procedure, Downhole, Drilling Report (Drilling Parameters and Mud are its
  sections) and Daily Report.

**Fix 1:**
- A timer tick on a tab that is hidden **and** clean, with a pending context, calls no saver. The outcome is
  NO_CHANGES, logged at debug.
- Edited, visible or unknown-state tabs are still blocked and reported.
- Every block now explains itself, e.g. "well 3 is selected but not loaded yet; the tab has not been opened since
  the selection changed".
- An explicit Save All still reports CONTEXT_BLOCKED.

**Root cause 2: Daily Report's own navigation (found by the M169 journey).**
- The timeline, "latest report of a section" and "after create" all call `load_report_by_id` directly. It never
  recorded the loaded report.
- So after a timeline click the **visible** tab showed a fully loaded report, yet every Save All or auto-save
  returned CONTEXT_BLOCKED ("report 1 is loaded while report 2 is selected").
- Reproduced in the real window with two reports of the same well and section.

**Fix 2:** `DrillTabBase.acknowledge_direct_load` records such a load only when:
- nothing newer is pending (or only the level currently being applied); and
- the record belongs to the well actually loaded.

A report of another well stays blocked. The guard itself is unchanged.

---

## D. Directional (M155/M156)

| Surface | File | Role | Maths |
|---|---|---|---|
| W6 › Well Trajectory Viewer | `tabs/trajectory_viewer.py` (486 lines) | **canonical**: plan, vertical section, 3D, compare/clearance, plan designer | `core.well_trajectory`, `core.trajectory_3d` |
| Plan designer | `tabs/well_plan_designer_panel.py` (719) | inside the viewer | `core.well_plan_designer` (M86 v2, M106 v1), `core.directional_plans` (revisions) |
| Compare / clearance | `tabs/trajectory_compare_panel.py` (540) | inside the viewer | `core.trajectory_compare` |
| 3D and layers | `tabs/trajectory_3d_view.py` (415), `tabs/trajectory_layers_panel.py` (249) | inside the viewer | `core.trajectory_layers` |
| Survey revisions | `tabs/survey_revision_panel.py` | immutable revisions | `core.survey_revisions` |
| W6 › Survey Data | `tabs/w6_Trajectory_Widget.py` | station editor | shared `core.survey_records.prepare_surveys` |
| W6 › Trajectory Plot (legacy) | `tabs/w6_Trajectory_Widget.py` | per-report 2D plan/side and 3D; **plot save, plot-data export** | shared `core.survey_records.plot_series`, `core.trajectory_plot` |
| `TrajectoryCalculationManager` | `tabs/w6_Trajectory_Widget.py:723` | `create_calculation`, no caller | none |
| `dialogs/planning_dialog.py` | — | time/activity planning, not a well path | — |

No duplicate solver exists: every surface uses the shared core modules, so no solver mathematics is at risk.

- The canonical workflow is the viewer.
- The legacy Trajectory Plot tab is **kept**: removing it would lose plot save and plot-data export.
- **Next:** port both to the viewer, then retire the tab and the unused manager.
- Legacy records stay readable; nothing was migrated or deleted.

---

## E. Pipe reference data (M157–M160)

### E.1 Model

`core/engineering/tubular_reference.py`:
- **Component types:** DP, HWDP, DC, TOOL_JOINT, CASING, TUBING, LINER.
- **Fields:** 12 engineering fields in canonical units. All are optional; `None` is shown as "unavailable", never
  as 0. Zero, negative, NaN, infinite, boolean and text values are refused.
- **Provenance:** `origin` is manufacturer, user or derived, together with document, URL, revision, page, units,
  licence and file fingerprint.
  - A manufacturer entry needs manufacturer, document and an explicit licence ("a public page is not a
    redistribution licence").
  - A derived entry must state its derivation.
- **Consistency:** OD/ID/drift/wall and tool-joint contradictions are refused.

Versioned sets (`tubular_reference_sets` / `tubular_reference_items`, additive):
- DRAFT → PUBLISHED. A published version is immutable; a revision is a new version that copies the items.
- A calculation stores `reference_snapshot`: the full spec plus set name, version and fingerprints. It verifies
  without the library and detects relabelling or edits.
- `snapshot_drift` reports newer versions instead of rewriting anything.

The older `drill_pipe_specs` table is unchanged. The dialog (Tools › Tubular Reference Library) has type, origin,
OD and text filters and a provenance pane. It cites only published items.

### E.2 Population (M158): BLOCKED

No pipe rows are shipped:
- None of the audited repositories contains a tubular dataset; welleng's data covers ISCWSA tool groups and Volve
  examples.
- API 5DP / 5CT tables are copyrighted standards.
- No manufacturer catalogue with a redistribution licence was reachable.

Users build their library from documents they are licensed to use. An owner decision is needed before any
manufacturer dataset is added.

### E.3 Warnings (M160)

**"Optional DrillPipe vendor reference unavailable (DRILLMASTER_DRILLPIPE_PATH / DrillPipe.xlsx)":** W13 logged
this as a WARNING on every start, for an optional file that is simply absent. It is now INFO; a file that exists
but cannot be read stays a WARNING.

**openpyxl "Data Validation extension is not supported and will be removed":**
- Reproduced with the golden fixture.
- Meaning: openpyxl drops x14 dropdown definitions from its in-memory model if that model is saved.
- DrillMaster never saves a user's source workbook. Normalisation writes a separate `*_clean.xlsx`, and the only
  in-place save targets our own export's provenance sheet.
- `core/workbook_io.py` turns exactly that warning into one INFO notice on the DDR import routes. Every other
  warning is re-emitted.
- The source SHA-256 is unchanged in the tests.

**Google Drive `DrillPipe.xlsx`:** NOT RUN. It was not needed for the diagnosis, and the user's workbook is never
modified or redistributed.

---

## F. External audit (M161/M162)

Exact revisions and licences were read through the GitHub API. Nothing was cloned into the product.

| Repository | Revision | Licence (API) | Language | Verdict |
|---|---|---|---|---|
| mhnajafi7/pdf-report-table-extractor | `fb1a0b863cb3` | Apache-2.0 | Python | known since M52; DrillMaster's own PDF route already covers it; not adopted |
| modelcontextprotocol/servers | `36380287ed3b` | NOASSERTION (mixed) | TypeScript | out of scope: no mandatory MCP |
| kornia/kornia | `ac4ce3cf088a` | Apache-2.0 | Python | out of scope: vision / GPU |
| KalyanKS-NLP/llm-engineer-toolkit | `3dc044494a1c` | Apache-2.0 | — | link list, no code to adopt |
| ShreshthSrivastav/DrillingAdvisor | `ba971ba72959` | none | Python | unusable (no licence) |
| jonnymaserati/welleng | `d29adf906b38` | Apache-2.0 | Python | owner-gated (ISCWSA); unchanged |
| BillyFrcs/DrillingEngineeringOperations | `5195e1129d93` | MIT | C#/C++/Python | ECD, hydrostatic, kill mud already have tested contracts; no benefit |
| Kukuruza24110/well-engineer | `ebd02d9b26b7` | none | JavaScript | unusable |
| dasvan/engineering-calculations | `684ba9ef9c13` | none | CSS | unusable |
| adityaparsad01/engineering-calculations | `7b6e9f4141f0` | ISC | TypeScript | not drilling-specific; not adopted |
| manjramkar/Drilling-Engineering | `3c0418b3f3cd` | none | Notebook | unusable |
| Otto-Destiny/3d_well_trajectory_visualization | `a66e754ce552` | none | HTML | unusable |
| juangjuang74-eng/drilling-engineer-toolkit | `8537e1df1dba` | MIT | Python | one 27 kB formula module; covered in-house; no pipe data |
| mengyangcup/drilling_engineering_design | `43342279c6e1` | none | Notebook | unusable |
| johnryan417/python-for-drilling-engineers | `61e88036e010` | none | HTML | unusable |
| Himageo2006/mud-engineer-pro | `e244ce1e2e8d` | none | HTML | unusable |
| f0nzie/volve-drilling | `3698c43d4adc` | none | R | unusable (code); Volve data has its own terms |
| jntran08/DataAnalyticsforEngineering | `823e1e53af94` | none | Notebook | unusable |
| ejbo2001/3D-directional-drilling-engine | `f96787d7c5c4` | GPL-3.0 | Python | excluded (GPL) |

**Ambiguous names** (several repositories share the name; the most plausible candidate is listed above):

| Name | Candidates |
|---|---|
| DrillingAdvisor | 4, none licensed |
| engineering-calculations | 4, one ISC |
| DataAnalyticsforEngineering | 2 |
| llm-engineer-toolkit | 4 |

**M162 decision:** nothing adopted, no new dependency. The earlier 50-source inventory (M52) was not re-audited in
this mission.

---

## G. Quality and CI

| Gate | Result |
|---|---|
| Local full suite on `9b4025d` | **5121 passed, 4 skipped (opt-in), 0 failed** in 2128.07 s (Py 3.11.2, offscreen Qt) |
| M141–M170 mutation catalog (28 mutants, complete) | **28 killed / 28**, 0 survived, 0 equivalent, 0 invalid, complete=True, 191 s |
| M121–M140 mutation catalog (complete) | **329 killed / 330**, 0 non-equivalent survivors, 1 declared equivalent (`SEC-empty-password-unlocks`, not counted as killed), 0 invalid, complete=True, 2847 s |
| Lint: ratchet population `core dialogs tabs tests` | 0 findings (ceiling 0) |
| Lint: E722/F821 over `.` | 0 findings |
| Exception ratchet | within ceiling. Two new handlers were made non-silent instead of raising the ceiling |
| Privacy check | 1458 files, 0 findings |
| Schema compatibility (old `0822a28` → `d5766be`) | 26/26 |
| Dependency / licence audit | 26 locked, findings 0, FAIL 0; regenerated after the last code change |

**Mutation survivors** found during the mission were fixed by tests, not by declaration:
- `M148-missing-row-accepted`: a redundant guard was folded into the comparability check.
- `M148-ownership-not-reproven`: an inconsistent decision payload is now tested.
- `M153-foreign-well-acknowledged`: the helper's contract is now tested directly.

The 4 opt-in skips (real DDR XLSX/PDF, real MinerU, Windows bundle) are not passes. The declared-equivalent mutant
of the M121–M140 catalog is not counted as killed.

### CI

| SHA | Workflow runs | Jobs (check runs) | Result |
|---|---|---|---|
| `d5766be` | Windows 42901403621, Source 42901403333 | 130128007115, 130128011843 / 130128011393 / 130128011857 | **CANCELLED** by the next push. Not a pass |
| `c20f5cd` | Windows 42903438335, Source 42903438339 | windows 130135216636; 3.11 130135315777; 3.12 130135316065; 3.13 130135315458 | **FAILED**: 3 failures (two index-plan assertions for the new `tubular_reference_items` indexes, stale `dependency_audit.json`), all fixed in `9b4025d` |
| `9b4025d` (final code) | Windows 43562099088, Source 43562099041 | windows 132347826381 ✅; 3.11 132347826725 ✅; 3.12 132347826463 ✅; 3.13 132347826713 ✅ | **SUCCESS** on all 4 jobs. Coverage (3.12, branch+line) **70.46 %** over 271 files (floor 45.50 %; baseline 70.01 %). Warnings: 32 occurrences in 9 groups, 1 repository-owned (large-file notice), 31 third-party. Windows: installer built UNSIGNED, uninstall PASS, M52 lifecycle stress 5/5 PASS with 0 native crashes |

The 12 third-party openpyxl "Data Validation extension" warnings in the CI summary come from tests that read
workbooks with openpyxl directly. Product reads go through `core/workbook_io.py` (M160), which swallows only that
warning.

**Crash-dump annotation on `c20f5cd` Windows.** That run carried a "fatal crash dump" annotation whose excerpt was
the index-plan assertion output with no parseable stack frames. `packaging/junit_report.py` runs `crash_excerpt`
only when pytest's exit code is non-zero, and it anchors on generic markers (`Current thread` among them). The
green `9b4025d` Windows run (same suite, 0 failures, exit 0) carries no such annotation, and the M52 stress
reported 0 native crashes and 0 new dumps. Conclusion: no evidence of an interpreter crash. Which text matched the
marker was not proven, so this is recorded as an observation and not as a fix.

### D51 (M143)

OPEN. No hang occurred in this mission's CI: the Windows release gate completed on `9b4025d` (and failed normally, without hanging, on `c20f5cd`). No new stack frame was captured, so the root cause is still unproven. No timeout was raised and no retry was added.

---

## H. Open work register (M142)

| Item | State | Owner / next step |
|---|---|---|
| D51 CI hang in the release gate | OPEN | needs a reproduction; the watchdog bound stays |
| D46 residual | RESOLVED with residual | reopens only on recurrence |
| D6 lineage | PARTIAL | the audited repair stands |
| D11 CRS | NOT ASSESSED | owner |
| D13 | OWNER REVIEW REQUIRED | owner |
| M151 deferred scalar corrections | PARTIAL | need a re-import; editing a scalar from the queue is not built |
| M152 MinerU description headers | PARTIAL | mapping coverage (needs a `PROFILE_RULES_VERSION` bump) |
| M156 legacy Trajectory Plot | PARTIAL | port plot save and data export to the viewer, then retire |
| M158 pipe data | BLOCKED (source rights) | owner to supply licensed documents |
| M159 / M165 module integration | OPEN | Architecture, Volumes, Hydraulics, Weight, Casing and T&D should store `reference_snapshot` |
| M161 earlier 50-source list | NOT RE-AUDITED | only the 19 named repositories were audited |
| Import files under the workbook's well | OBSERVED (pre-existing) | owner decision on the identity rule |
| Licences / dependencies | OWNER REVIEW REQUIRED | ISCWSA/welleng, pwptemp/torque_drag (LGPL), PyMuPDF (AGPL), OCR/onnxruntime, AI models/GPU, MinerU, qtribbon |
| Engineering decisions | OWNER REVIEW REQUIRED | kill sheet TRAINING AID, 7.48 vs 7.48052, currency, CRS, method approvals |
| Security / release | OWNER REVIEW REQUIRED | DB encryption / HMAC / DPAPI / SQLCipher, Windows ACL, idle-lock default, signing, release |
| Acceptance | OWNER REVIEW REQUIRED | Windows interactive, field |
