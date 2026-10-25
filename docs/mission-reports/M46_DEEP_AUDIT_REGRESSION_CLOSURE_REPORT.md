# M46 — Deep audit, regression closure, workspace integrity, verified push

Repository `asgareyvazi/Drill-master`, branch `arena/72010272-drill-master`.
Start `bea296856a22b0411aeec24cdf25b65b5162dfaa` (M45 report tip). Code tip
`53749e018578d4ffc2600ad5af85fb8c2f6fdae9`. The report commit is the one that adds this file.
Status: **UNSIGNED**. This is not a release, acceptance or approval document.
Every number below comes from a command run during M46 unless it is marked
"copied" (taken from an earlier report or run and not re-measured).

## A. Summary

* M46 re-audited the M44/M45 claims against the code, using fresh tests and
  independent reproductions. It found **six defects**:
  * **P1: H1, silent data loss.** A write was lost without any error when
    the hierarchy refresh overlapped it.
  * **P2:**
    * **T1:** the test suite depended on file order.
    * **S1–S3:** fallback search and highlighting disagreed with the FTS5
      index.
    * **W1:** the survey editor showed rows that its Save could not write.
* Every defect has a root cause, a test that fails on the old code and a
  minimal fix. The fixes are pushed and verified on the remote with
  `ls-remote`.
* **Shared-connection limitation.** The application-wide shared SQLite
  connection was already documented in `docs/DATABASE_OPERATIONS.md`. It was
  not replaced, because that would be a broad change. M46 removed the only
  background worker that still used it (H1) and updated the documentation.
* **Search.** The normalisation rules changed, so `NORMALIZATION_VERSION`
  is now 2 and indexes built under v1 are rebuilt.
* **Fresh evidence** (all on the code tip `53749e0`):
  * full suite: 3170 passed, 0 failed, 4 skipped;
  * reverse-order full suite: 3170 passed, 0 failed, 4 skipped;
  * hostile-order run: 92 passed (12 failed before T1);
  * mutation: 29 real mutants, 29/29 killed, none declared equivalent;
  * schema compatibility: 26/26;
  * workflows: 24/24 steps;
  * 7 offscreen screenshots;
  * exact-SHA CI: Source release gate and Windows release validation both succeeded on the code tip.
* **Not done:** Windows desktop acceptance, signing and field validation.
  These are owner-gated. A CI runner is not acceptance.

## B. Git

| Item | Start of M46 | End of M46 |
|---|---|---|
| Path | `/home/user/Drill-master` | same |
| Branch / upstream | `arena/72010272-drill-master` / `origin/arena/72010272-drill-master` | same |
| HEAD | sandbox checkout was a stale graft `4336ea3`. Recovered without data loss: temp-index comparison, then CAS `update-ref` to the remote tip `bea2968`, then `read-tree`, then `fetch --unshallow` | the report commit (code tip `53749e0` + this report and its README row); equal to remote by `ls-remote` |
| Remote | `bea2968` (0 ahead / 0 behind after recovery) | equal to local HEAD (`ls-remote`, recorded at every push) |
| Working tree | clean after recovery; `diff --check` clean | clean; no untracked files |
| Remotes | `origin` → `github.com/asgareyvazi/Drill-master` (credentials not printed) | same |
| Other branch | `drill-Master` = `e3fa42a`, not touched | not touched |
| M44 / M45 order | M44 `be70917`…`f939fbe`, report `0822a28`; M45 `d52fbd9`…`f933081` (11 commits, 32 files), report `bea2968` | unchanged (no history rewrite) |

M46 commits. Each was pushed separately and confirmed with `ls-remote`. A
privacy check ran after `git add` and before every push:

| Commit | Package |
|---|---|
| `973f8c0` | test(isolation): restore the session principal after every test (T1) |
| `d26a071` | fix(search): same match rules in FTS5, fallback and highlight (normalisation v2) (S1–S3) |
| `5125a3b` | fix(survey): editor without a report lists only well-level rows (W1) |
| `6382e1e` | fix(hierarchy): worker reads on its own read-only connection (H1) |
| `f734204` | test(links): full-state atomicity, read-only denial, two-instance race |
| `66c9a7e` | test(3d): draw coalescing and hide/show/close lifecycle |
| `af41105` | chore(quality): schema compatibility and M46 mutation tools |
| `5896e3d` | ci(windows): run the M46 regression modules on the Windows gate |
| `1637b57` | docs(evidence): M46 workflow script and offscreen screenshots |
| `53749e0` | test(search): pin non-ASCII-base Latin letters to FTS5 behaviour |

Diff `bea2968..53749e0`: 27 files, 1708 insertions, 29 deletions. No caches, virtualenvs, keys or
logs are committed.

## C. Traceability of M44/M45 claims

How to read the table:

* **Fresh** means re-run or re-derived in M46 on the code tip.
* **Copied** means taken from an earlier report and not re-measured.
* "Full suite" means the fresh M46 full-suite run (section E).
* **Independent** means the reference was not computed by the function under
  test.

### M44

| Claim | File / function | Data source | Test (assertion) | Independent reproduction | Status | Action |
|---|---|---|---|---|---|---|
| Home KPIs equal the fixture; "No data" instead of 0; tooltip definitions | `core/operations_dashboard.py`, `tabs/home_tab.py` | `tests/synthetic_operations.py` | `test_operations_dashboard::test_synthetic_kpis_match_the_fixture`, `test_empty_database_reports_no_data_instead_of_zero`, `test_every_kpi_has_its_written_definition` | Screenshot `m46_home_dashboard.png`: 5 wells, 9 reports, 6 reports in 7 days, 1 well needing review. These match the fixture definition (4 SYN wells + the bootstrap Default well; 6 + 2 + 1 reports) | PASS (fresh) | — |
| Attention list and drill-down navigation | `operations_dashboard`, `MainWindow.navigate_to` | fixture | `test_flags_and_drill_down_targets_per_well`, `test_m44_ui::test_dashboard_drill_down_payloads`, `test_navigate_to_routes_dashboard_payloads` | Screenshot: the SYN-QA-03 ERROR and WARNING flags | PASS (fresh) | — |
| Plan / VS, units, azimuth, selection | `core/well_trajectory.py`, `tabs/trajectory_viewer.py` | fixture | `test_m44_ui::test_viewer_*` (7 tests), `test_well_trajectory::test_user_vs_azimuth_*`, `test_display_unit_conversions` | `workflow_m46.py` survey step 8: feet are exactly m × 3.2808… | PASS (fresh) | — |
| Invalid or empty survey: no fabricated path | `compose_well_trajectory`, `scene_from_trajectory` | fixture SYN-QA-03, SYN-VERT-02 | `test_invalid_rows_are_excluded_and_reported`, `test_no_rows_is_no_data_and_not_drawable`, `test_trajectory_3d::test_excluded_rows_never_become_points` | Workflow survey step 9; screenshot `m46_trajectory_invalid_survey.png` (3 rows excluded, only MD 0 and 100 drawn) | PASS (fresh) | — |
| EOWR / Export / REST coordinate fix: stored per-report frames are not used; the whole well is recomposed | `report_engine._composed_surveys`, `professional_export` Survey sheet, `rest_api.get_trajectory` | fixture SYN-DEV-01 (66 rows, 6 reports) | `test_eowr_and_exports_use_the_composed_trajectory` | **Independent minimum-curvature implementation** in `tools/quality/workflow_m46.py` (not imported from the app). REST, EOWR and the Excel export all equal it at all 61 stations (max abs diff < 1e-6 m). Analytic J-profile end point: TVD 1612.06, HD 586.74 (R = 30/rad(2°) = 859.437 m). Stored last-report TVD 1378.88 is copied from M44 | PASS (fresh) | Root cause (copied from M44, re-checked): consumers read stored per-report derived columns. All four consumers found by `grep compose_well_trajectory` now recompose: REST, EOWR, professional export, dashboard and viewer |
| Document import and review; OCR stays unapproved until a decision | `core/document_library.py` (`default_decisions`, `import_reviewed`) | generated SYN files; stand-in OCR | `test_ocr_text_is_stored_only_after_explicit_approval`, `test_documents_tab::test_review_dialog_approval_edit_and_skip` | Workflow document steps 2–5 (stand-in OCR engine, no model) | PASS (fresh) | — |
| Batch isolation | `extract_batch` | generated bad files | `test_batch_isolates_failures`, `test_import_batch_isolation` | — | PASS (fresh) | — |
| Hash dedup, original kept | `duplicate_of` | generated | `test_duplicate_content_is_refused_even_under_another_name` | Workflow document step 13 | PASS (fresh) | — |
| Audit and rollback of imports | `import_reviewed` | generated | `test_failure_mid_import_rolls_back_document_pages_and_audit` | — | PASS (fresh) | — |
| FTS5 offline, with fallback without FTS5 | `DocumentLibrary.search`, `_scan_search` | generated | `test_search_falls_back_to_substring_scan_without_fts5` | Defects **S1–S3** found here (section D) | PASS after fix | Fixed in `d26a071` |

### M45

| Claim | File / function | Test (assertion) | Independent reproduction | Status | Action |
|---|---|---|---|---|---|
| Create / change / remove a link only after explicit confirmation | `core/document_links.py`, `tabs/document_link_dialog.py` | `test_m45_ui::test_link_dialog_suggests_but_links_only_after_confirmation`, `test_cancelled_dialog_changes_nothing` | Workflow document step 8: links stay 0 until `create_link` | PASS (fresh) | — |
| Related panels in Well Info and Daily Report; page anchor | `well_info_tab`, `daily_report_tab` | `test_well_page_lists_linked_documents_and_opens_them`, `test_report_page_lists_its_documents_and_follows_link_changes` | Workflow step 9 | PASS (fresh) | "Change link…" carries the existing anchor page (`LinkDocumentDialog(current=…)` → `set_anchor_page`), read in code |
| Duplicates refused in service and schema | `_duplicate`, `uq_document_links_target` / `uq_document_links_well_level` | `test_duplicate_links_are_refused_by_service_and_schema` | **New:** two `DatabaseManager` instances racing on one file → 1 link, 1 audit row, 3 × `duplicate` (`test_document_links_audit_m46`, 6/6 stable reruns) | PASS (fresh) | — |
| Audit failure rolls back; atomicity | `_audit`, `_run` | `test_audit_failure_rolls_*` | **New:** byte-identical links, audits, documents and pages after a failed change or removal, and after a commit failure that happens after the audit row was added | PASS (fresh) | Assertions strengthened (`f734204`) |
| Report must belong to the well (no cross-well id tampering) | `_validate_target`, ORM ownership guard | `test_invalid_targets_*`, `test_ownership_guard_*` | **New:** the change path is refused too (`report_well_mismatch`, `page_missing`) | PASS (fresh) | — |
| Permission enforced at the data layer, no bypass | `enforce_authorization` | `test_link_permission_is_enforced_at_the_data_layer` | **New:** the read-only principal is denied change, remove and create. Each denial writes one `authorization_denied` audit row and nothing else | PASS (fresh) | — |
| Cascades; removing a link keeps the document; FKs | schema `ON DELETE CASCADE` (×3) | `test_report_delete_*`, `test_well_delete_*`, `test_document_delete_*`, `test_remove_link_keeps_the_document_and_is_audited` | `schema_compat_check.py`: FK list, `foreign_key_check` empty, integrity ok | PASS (fresh) | — |
| Migration; an M44 database still opens; orphans | `_apply_safe_schema_upgrades` | `test_existing_database_gains_the_link_table_without_losing_documents` | **`tools/quality/schema_compat_check.py` 26/26.** It covers 4 phases: M44 code creates the DB; an injected failure leaves schema and rows unchanged; current code upgrades it idempotently; M44 code reopens, lists, searches and deletes with no orphans | PASS (fresh) | — |
| Persian/Arabic folding, digits, ZWNJ, diacritics, tatweel | `core/search_normalization.py` | `test_search_normalization` (16) | Workflow steps 6–7 | PASS (fresh) | — |
| Phrases and identifiers precise; fallback equals FTS5; every hit highlighted | `parse_query`, `fts_match_expression`, `_scan_search`, `find_spans` | **New** `test_search_parity_m46` (8): a generated corpus of 250 pages and >200 queries gives identical FTS5 and fallback page sets, with spans on every hit | Probe before the fix: `SYN-DEV-01` fallback hit SYN-DEV-012; `cafe` and `SYN_DEV` FTS hits had no highlight; `می شود` fallback found nothing | **FAIL → fixed** (S1–S3) | `d26a071`, `53749e0`; `NORMALIZATION_VERSION` 2 |
| Reindex keeps the original text | `rebuild_index` | `test_documents_indexed_before_the_normalisation_are_found_after_rebuild` | Workflow step 12; **new** `test_a_v1_index_is_rebuilt_under_v2` | PASS (fresh) | — |
| Safe FTS (no injection) | `_quote` | **new** `test_hostile_and_degenerate_queries_are_plain_words` | — | PASS (fresh) | — |
| 3D uses the shared composer, axes and units; selection is synced | `core/trajectory_3d.py`, `tabs/trajectory_3d_view.py` | `test_trajectory_3d` (19) | `test_build_and_turn_matches_independent_circle_geometry` (copied design); screenshots show the same station in 3D and Plan | PASS (fresh) | — |
| Camera changes only the view | `apply_preset`, `zoom`, `reset_view` | `test_presets_reset_and_zoom_change_only_the_camera` | — | PASS (fresh) | — |
| Qt/Matplotlib lifecycle: no callback after destroy; timer safe through hide/show/close | `_request_draw`, `_draw_now`, `showEvent`, `draw_idle` override | `test_a_destroyed_view_leaves_no_pending_draw`, `test_matplotlib_redraw_requests_cannot_outlive_the_canvas`, **new** `test_trajectory_3d_lifecycle_m46` (2) | 7 lifecycle mutants killed | PASS (fresh, offscreen) | — |

## D. Defects

| ID | Severity | Defect | Root cause | Test failing on the old code (proof) | Fix | Impact on permissions / audit / migration |
|---|---|---|---|---|---|---|
| H1 | **P1** | A save made while the hierarchy refresh was running was **silently lost**: commit returned, nothing was stored, no error was raised. The worker could also read uncommitted rows | All sessions share one SQLite connection (`StaticPool`, known and documented). `HierarchyWorker` read through it from a background thread; returning its session to the pool rolled the shared connection back | `test_hierarchy_worker_isolation_m46`. On `bea2968` the in-flight row is gone: stored `['DC001','SYN-HC0']`, expected `+['SYN-HC1']`. A deterministic interleaving, not a timing race | `HierarchyWorker.run` reads through `core.export_jobs.worker_database` (own read-only connection, the M43 facility already used by the Export Center and Home KPI workers) | None. The read-only connection carries the same authorization state and is gated by the restore `MaintenanceGate`. Docs updated |
| T1 | P2 | The suite was order-dependent. A user signed in by `test_p0_permissions` (and others) leaked into later tests, so 12 M44 tests failed in a hostile order. The default alphabetical order hid it | `core.permissions.permissions` is a process singleton and several modules never restore it | Hostile order before the fix: **12 failed** (9 in `test_document_library`, 3 in `test_documents_tab`). The leaked user id fails the audit FK, so imports roll back | Autouse fixture in `tests/conftest.py` restores the previous principal after each test. Nothing is granted and no user is faked; each test still signs in what it needs | No permission test was weakened. `test_test_isolation_m46` (4) covers both the file-order and module-fixture cases |
| S1 | P2 | Without FTS5, `SYN-DEV-01` also found `SYN-DEV-012` | The fallback treated every query word as an independent prefix and ignored phrases | `test_fallback_keeps_identifier_precision` | Shared `text_matches(groups)` with FTS5 semantics: single word = prefix, phrase or identifier = exact adjacent tokens | Search only. The index signature was bumped |
| S2 | P2 | Without FTS5, a half-space word typed with a space was not found | The fallback had no half-space alternative | `test_fallback_finds_a_half_space_word_typed_with_a_space` | `query_alternatives`, shared by FTS5 and the fallback | Search only |
| S3 | P2 | FTS5 hits for `cafe`→`café` and `SYN_DEV` had no highlight and no line to open | FTS5 `unicode61 remove_diacritics 2` folds Latin diacritics and splits on `_`; the Python tokenizer did neither | `test_underscore_and_latin_diacritics_follow_the_fts_tokenizer`, generated-corpus parity test | v2: Latin letters whose base is ASCII are folded, U+0300–036F are removed, `_` separates tokens. Letters with a non-ASCII base (Ǣ, Ǿ, Ǯ) are deliberately not folded, which matches FTS5 | Original text, filenames and operator decisions are untouched (normalisation is index and comparison only) |
| W1 | P2 | Survey editor with a well and no report listed **every report's** rows: mixed per-report TVD/N/E frames under the green "Calculated" highlight. Save (scope `(well, None)`) then refused | `SurveyDataTab.load_data` loaded the well scope while `save_data` wrote the well-level scope | `test_survey_editor_scope_m46`. Old code: 5 rows from 3 frames instead of 1, and Save refused | Without a report, only rows with `report_id IS NULL` are listed (same scope as Save). The whole-well view stays the Well Trajectory Viewer | No data corruption was possible before the fix (Save refused and rolled back) |

Findings that are **not defects:**

* Concurrent writes from several threads of one `DatabaseManager` are not
  supported. This is a documented limitation and the reason for H1. A probe
  showed lost and duplicated audit rows when 4 threads of one manager wrote
  at once.
* Two application instances on one file are supported and race correctly
  (tested).
* Denied operations write `authorization_denied` audit rows. This is
  intended.

## E. Tests

Environment: Linux, offscreen Qt (`QT_QPA_PLATFORM=offscreen`, bundled
libraries `/home/user/qt-libs`), Python 3.11.2, PySide6 6.8.1.1,
matplotlib 3.9.3, pytest 9.1.1. No stubs replace product code in these runs.
These are **not** Windows desktop results.

| Run | Command | SHA | Result | Time |
|---|---|---|---|---|
| Baseline | `python -m pytest -p no:cacheprovider --tb=short -rfEs --continue-on-collection-errors tests` | `bea2968` | 3148 passed, 0 failed, 4 skipped | 666.54 s |
| Full suite | same | `5896e3d` | 3169 passed, 0 failed, 4 skipped | 663.18 s |
| **Full suite (final)** | same | `53749e018578d4ffc2600ad5af85fb8c2f6fdae9` | **3170 passed, 0 failed, 4 skipped** | 672.92 s |
| **Reverse file order** | same, with `$(ls tests/test_*.py \| sort -r)` | `53749e018578d4ffc2600ad5af85fb8c2f6fdae9` | **3170 passed, 0 failed, 4 skipped** | 674.75 s |
| Hostile order | `-p no:randomly tests/test_p0_permissions.py tests/test_document_library.py tests/test_operations_dashboard.py tests/test_well_trajectory.py tests/test_documents_tab.py tests/test_test_isolation_m46.py` | `bea2968` + T1 fix / final | 12 failed before T1; 92 passed, 0 failed after | — |
| Flaky reruns | `test_document_links_audit_m46` ×6, `test_trajectory_3d_lifecycle_m46` ×3, M46 modules ×5 | final | all passed (links 6 × 5/5, 3D 3 × 2/2; all 6 M46 modules 5 × 22/22) | — |

Count change against the baseline: +22 tests, all new M46 tests. That is
isolation 4 (2 file-order + 2 module-fixture), search parity 8, survey
scope 2, hierarchy 1, links 5 and 3D 2. 3148 + 22 = 3170. The 4 skips are
unchanged and justified:

* 2 × `test_ddr_acceptance.py:33`: real DDR acceptance is opt-in and must
  not use real data.
* `test_mineru_real_integration.py:26`: no MinerU installation.
* `test_packaging_smoke.py:218`: no Windows bundle on Linux.

**Coverage.** CI Source gate on the code tip: 57.20% branch+line over 200 tracked files (43733/76455), from the run 40182842472 annotation (the floor stays
45.50% and was not changed). Earlier value 57.11% over 200 files, copied
from the `f933081` and `5896e3d`-era runs.

**Mutation** (fresh, complete run of `tools/quality/mutation_m46.py` on the
final tree): 29 mutants, 29 killed, 0 survivors, 0 declared equivalent, 0 invalid, complete run, 82 s, exit 0.

* The tool copies the working tree into a temporary directory and requires a
  passing baseline (82 tests passed).
* Each mutant's snippet must occur exactly once.
* The tool exits non-zero on any survivor or invalid mutant.
* Groups: T1 (2), search (10), W1 (2), H1 (1), links (8), 3D (6).
* The complete runs on `1637b57` (28 killed + 1 then-declared equivalent)
  and on `53749e0` (29/29) are both recorded; the `53749e0` run is the
  result that counts.
* The first M46 run had 2 survivors:
  * `T1-snapshot` was a real gap. It was killed by the module-fixture
    isolation tests.
  * `S-latin-ascii-guard` had been declared "equivalent" with a wrong
    justification. A check found 9 letters whose base is not ASCII, so the
    declaration was removed and a test kills the mutant.
* No mutant is declared equivalent in the final run.
* The M45 mutation figures (links 15/16, normalisation 12/12, UI 15/15,
  3D 22/22) are **copied, not fresh**. The M45 script was not preserved;
  M46 re-covered the link and 3D contracts with new mutants.

**Compatibility.** `tools/quality/schema_compat_check.py --old-ref 0822a28`
against the final tree: 26/26 checks passed (old `0822a28`, new `53749e0`).

**Workflows.** `tools/quality/workflow_m46.py`: 24/24 steps PASS (14
document, 10 survey). The OCR step uses a deterministic stand-in engine and
says nothing about real OCR accuracy.

**Gates on the final tree:**

* lint debt 749, ceiling 749 (not raised; M46 added 0);
* exception scan within its ceiling;
* privacy check 0 findings.

**Not run:**

* native Windows desktop interaction;
* real OCR models;
* real DDR files (opt-in, not used).

## F. UI evidence

Captured by `tools/screenshots/capture_m46.py` from the real `MainWindow`
on a throw-away synthetic database. Offscreen Linux, raster rendering; not a
Windows desktop. All 7 PNGs are reviewed and pinned by SHA-256 in
`tools/privacy/policy.json`.

| File | Shows |
|---|---|
| `m46-screenshots/m46_home_dashboard.png` | Home KPIs and the attention list (fixture values) |
| `m46-screenshots/m46_search_identifier_precision.png` | `SYN-DEV-01`: 1 page; the SYN-DEV-012 note is not matched (S1) |
| `m46-screenshots/m46_search_latin_diacritics.png` | `cafe` highlights the original `café` (S3) |
| `m46-screenshots/m46_survey_editor_well_scope.png` | SYN-DONE-04 without a report: only the well-level row (W1) |
| `m46-screenshots/m46_trajectory_3d_picked_station.png` | 3D view with a picked station (MD 1350 m) |
| `m46-screenshots/m46_trajectory_plan_vs.png` | Plan view with the same station |
| `m46-screenshots/m46_trajectory_invalid_survey.png` | SYN-QA-03: review required, 3 rows excluded, only valid stations drawn |

During review, the first capture of the trajectory shots showed the "Well:"
combo on a different well from the viewer. The capture script had called
`viewer.select_well` directly. It now selects through
`TrajectoryWidget.on_well_changed` (the UI path) and the images were
re-captured. The M45 images were checked and are consistent.

Linked document and Well Info / Daily Report related panels: M45 images
`m45-screenshots/*` (copied, not re-captured). The same behaviour was
re-verified by workflow steps 8–9.

## G. CI

Concurrency cancels runs of superseded SHAs. Cancelled runs are listed for
completeness and count for nothing.

| SHA | Source release gate | Windows release validation |
|---|---|---|
| `973f8c0`…`af41105` | cancelled (superseded) | cancelled (superseded) |
| `5896e3d` | 40181716618 cancelled | **40181716606 success** (`windows-2022`, Python 3.12.10, PySide6 6.8.1.1 from the lock file; first run with the M46 modules) |
| `1637b57` | 40182671914 cancelled (superseded) | 40182671907 cancelled (superseded) |
| **`53749e018578d4ffc2600ad5af85fb8c2f6fdae9`** (code tip) | **40182842472 success (source 3.11 / 3.12 / 3.13 on `ubuntu-24.04`; coverage 57.20%)** | **40182842469 success (`windows-2022`, includes the 6 M46 modules)** |

Links: `https://github.com/asgareyvazi/Drill-master/actions/runs/<id>`.
Actions remain pinned by commit SHA; M46 changed no action. The Windows
gate now also runs the 6 M46 modules, which are pinned in
`REQUIRED_MODULES` of `tests/test_windows_release_gate_contract.py`.

**Earlier failure history (copied; logs are not reachable from this sandbox,
evidence comes from check-run annotations):**

* **Run 40168089020 (`780880f`):** `Windows fatal exception: stack overflow`,
  pytest exit -1073741571 (0xC00000FD), no JUnit report. The crash-surviving
  breadcrumb named `test_trajectory_3d.py::test_clicking_a_station_selects_the_real_station_everywhere`,
  and the innermost frame is in the `viewer` fixture (`test_trajectory_3d.py:181`).
* **Run 40169057891 (`27c5ad5`):** teardown `RuntimeError: Internal C++
  object (FigureCanvasQTAgg) already deleted` at `backend_qt.py:495`.
* **Fix and later runs:** the owned draw timer plus the `draw_idle` override
  (`f933081`) was followed by green Windows runs on `f933081`, `bea2968` and
  `5896e3d`.

The stack-overflow **cause is not proven**. The evidence is consistent with
re-entrant Matplotlib/Qt redraws during widget teardown, but the native stack
was not captured.

## H. Security, privacy, licences, M43 history

* **Authorization:**
  * Links are authorized at the data layer (create, change and remove all
    tested with a read-only principal).
  * No cross-well report ids are accepted, on create or change.
  * Audit rows are written in the same transaction (failure → full
    rollback, tested including a commit failure).
  * FTS queries are always quoted (an injection-shaped query is tested).
* **Logs:** link failures log exception type names only.
* **Scope:** this is not a full security audit.
* **Privacy:**
  * `tools/privacy/privacy_check.py` gated every push (0 findings).
  * Synthetic data only.
  * The 7 new PNGs are reviewed and pinned.
  * No real DDR or main-branch samples were opened.
* **Licences and dependencies:**
  * No new dependency.
  * PyMuPDF (AGPL/commercial) and PP-OCR/rapidocr model weights remain
    **owner decisions**.
* **M43 history:** a normal commit does not purge history. History cleaning
  is owner-gated and was not done.

## I. Remaining items

| Item | Owner |
|---|---|
| The highlighter marks each word of a phrase query as a prefix anywhere on the page (e.g. "SYN" inside "SYNTHETIC" for the query `SYN-DEV-01`). Page selection is correct; only the highlight over-marks (P3) | agent (next mission) |
| U+1E9B (long s with dot): FTS5 folds it to U+017F, the Python normaliser does not. Mismatch only for a query typed as "ſ…" (P3, documented in a test) | agent |
| A whitespace-only link note is stored as `""` rather than NULL (P3) | agent |
| Per-thread connections, which would replace `StaticPool` and make worker writes possible: broad change, needs its own tested mission | owner decision |
| Windows desktop / field / production acceptance; signing; release tag | owner |
| PyMuPDF and OCR model licence choice | owner |
| History purge of earlier real data (M43) | owner |

## J. Links

* M45 report: `docs/mission-reports/M45_DOCUMENT_TRACEABILITY_SEARCH_3D_REPORT.md`
* M44 report: `docs/mission-reports/M44_CONNECTED_CAPABILITIES_REPORT.md`
* Database limitations: `docs/DATABASE_OPERATIONS.md` ("Known limitations")
* Tools: `tools/quality/mutation_m46.py`, `tools/quality/schema_compat_check.py`,
  `tools/quality/workflow_m46.py`, `tools/screenshots/capture_m46.py`
* Privacy procedure: `docs/privacy/PRIVACY_CHECK.md`
