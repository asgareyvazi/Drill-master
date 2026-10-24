# M44 — Connected product capabilities: operations dashboard, trajectory viewer, reviewed document import and search

Mission M44, branch `arena/72010272-drill-master`, base `fe04c00bae22b3a839fa1d47ae437d670c93980d`
(M43 report tip). Written 2026-10-24. Repository documentation is English; every number
below comes from a command run in this mission (commands are given in section 5).

## 1. Final status

**COMPLETE (code), OWNER_GATED (release).** Every engineering item in the mission brief is
delivered as wired, visible, tested product behaviour, with three bounded exceptions
recorded in section 9: no 3D in the new viewer, no semantic search, and OCR verified
on synthetic images only. The installer remains **UNSIGNED**; nothing in this report
claims release readiness, Windows/operator acceptance or field validation.

## 2. Capabilities (behaviour · UI location · data source)

| Capability | Behaviour | Where in the UI | Data source |
|---|---|---|---|
| Operations dashboard | 11 KPIs (wells by status, daily reports, reports in 7 d, latest report, NPT hours and NPT share in 7 d, wells needing review, DDR imports in 7 d). Each card's tooltip is its written definition (`KPI_DEFINITIONS`, naming the records it counts); a value that cannot be computed shows "No data" (state `no_data`), never 0. Also: a wells table with latest report, depth (or "not reported"), days since report and survey MD; a "Needs attention" list (ERROR/WARNING/INFO); recent reports; a System panel. Loads in a worker on deferred first show; Refresh button and timer. | `🏠 Home` tab | `core/operations_dashboard.build_snapshot` reads wells, daily_reports, time logs, surveys and import audit; the System panel reads the engine's real database file, verified backups and autosave timers |
| Drill-down | A selected well opens Well Info, its latest report or the trajectory viewer; a QA flag opens the viewer on that well | Home → Open well / Open latest report / Open trajectory | `main_window.navigate_to`, `SelectionManager` |
| Whole-well trajectory viewer | Plan view (true north up, N/E metres from the tie-on), Vertical Section with an explicit azimuth (closure or user value) shown in the axis title; station markers; selected-station panel (MD, inc, azi, TVD, N/E, VS, DLS, source report ids); units m and °/30 m or ft and °/100 ft; equal-aspect toggle; data-check list. READY / REVIEW_REQUIRED / INSUFFICIENT_DATA banner; nothing is drawn when the data cannot support a path | `📍 Trajectory` → `Well Trajectory Viewer` | `core/well_trajectory.compose_well_trajectory`: stored survey rows across all reports, de-duplicated and conflict-checked, recomputed once with the existing minimum-curvature engine |
| Reviewed document import | Batch extraction in a worker thread with no DB access and cancel support. Review dialog: approve, edit or reject each page; OCR pages start unapproved; duplicates and unimportable files shown blocked. Each file imports atomically with a `document_import` audit record; corrupt, encrypted, empty, oversized, unknown and textless inputs are reported and never stop the batch | `📄 Documents` → `Import documents…` | Files chosen by the user. New tables `documents` and `document_pages`, write/delete policy `can_import` |
| Local document search | SQLite FTS5 (in-memory index rebuilt from stored, reviewed pages) with prefix matching. Each hit gives file, page or line range, review status and a snippet; opening a hit shows the stored source text with highlighted terms. Substring fallback when FTS5 is unavailable. No network | `📄 Documents` → search box | `document_pages.text` (reviewed text only) |
| Login fix | Auto-login no longer crashes; one session-user shape for every login path | app start | `core/permissions.session_user` |

The complete workflow (entry → result → detail) is exercised by tests and screenshots:
synthetic reports and surveys in a temp DB → dashboard KPIs and QA flags → drill-down → viewer
station detail; and synthetic files → review → import → search hit → source page.

## 3. Code changes

M44 commits on top of `fe04c00` (all pushed; 34 files changed excluding screenshots,
+4903/−754):

| Commit | Package |
|---|---|
| `be70917` | feat(trajectory): whole-well composer (`core/well_trajectory.py`); EOWR, professional export and REST now use the composed path instead of mixing per-report frames |
| `7fbdcc9` | feat(dashboard): `core/operations_dashboard.py` |
| `fe1058a` | fix(charts): `tabs/w12_Analysis.py` no longer sets pyqtgraph `useOpenGL` globally |
| `c8f3521` | fix(login): `session_user`, auto-login `TypeError` |
| `53a1aa9` | feat(ui): new Home dashboard, trajectory viewer, workers, navigation, status-bar well label, screenshot tool |
| `97676ce` | fix(privacy): pin the eight reviewed screenshots by SHA-256 (fixes the red source gate on `53a1aa9`, see section 11) |
| `e09fccf` | feat(documents): `core/document_library.py`, `tabs/documents_tab.py`, models, table policy, optional OCR requirements |
| `23a2bc2` | test(import): DDR batch isolation regression test |
| `f939fbe` | ci(windows): the Windows release gate now also runs the five M44 test modules (trajectory, dashboard, document library, documents tab, batch isolation) |

Schema: two new tables (`documents` with `uq_documents_sha256`; `document_pages` with FK
`ON DELETE CASCADE` and `uq_document_pages_page`). They are library-wide (no well FK, so well
deletion is unaffected) and created by the existing `create_all` path on fresh and upgraded
databases. `tests/test_model_registry.py` (fresh/upgraded equivalence) and
`tests/test_data_layer_authorization.py` (every table has a policy) pass. No money column, no
existing column and no migration of existing data changed.

## 4. Libraries

| Library | Version | Licence | Status | Reason / experiment |
|---|---|---|---|---|
| pyqtgraph | 0.13.7 (existing) | MIT | used | Interactive plan/VS plots in the viewer; already a core requirement, so no new dependency |
| PyMuPDF | 1.24.14 (existing) | AGPL-3.0 or commercial (existing dependency; licence status is an owner decision) | used | PDF text layer and page rendering for OCR |
| SQLite FTS5 | stdlib `sqlite3` (SQLite 3.40.1 locally) | public domain | used | Verified locally on Linux. From `f939fbe` the Windows release gate runs `tests/test_document_library.py`, which asserts the FTS5 path, so the Windows result in section 11 is the Windows evidence. The substring fallback for interpreters without FTS5 is tested |
| rapidocr ([RapidAI/RapidOCR](https://github.com/RapidAI/RapidOCR)) | 3.10.0 | Apache-2.0 (code); the bundled PP-OCR ONNX model licence is for the owner to verify | **optional** (`requirements-optional.txt`) | Pure-Python wheel, 27.3 MB, Python ≥3.8, models bundled in the wheel. Dependencies: opencv-python-headless, numpy, shapely, pyclipper, Pillow, PyYAML, omegaconf, tqdm, requests, colorlog, six. Experiment in a separate venv: init 0.51 s, 2.96 s per page; this mission's end-to-end run on a synthetic scanned PDF read both lines correctly at engine score 0.989 with status `needs_review`. A degraded synthetic image gave wrong text at 0.947, so OCR text always needs human review |
| onnxruntime | 1.31.0 | MIT | **optional** | Python ≥3.11 (PyPI metadata); win_amd64 wheels for cp311–cp314, about 14.9 MB; dependencies flatbuffers, numpy, packaging, protobuf |
| rapidocr_onnxruntime | — | — | rejected | Older package line, superseded by `rapidocr` |
| PaddleOCR | — | — | rejected | Requires the PaddlePaddle framework: much larger install for no gain over the same PP-OCR models via ONNX |
| pytesseract | 0.3.13 (already optional) | — | not used for M44 | Needs an external Tesseract binary install; not offline-installable from pip alone |
| Matplotlib | 3.9.3 (existing) | — | not used for the viewer | pyqtgraph already gives interactive pan/zoom/picking in Qt |
| PyVista | — | — | not added | VTK-based and heavy; 3D is optional in the brief and was not delivered (section 9) |
| welleng | — | — | not added | The existing minimum-curvature engine plus the composer cover the need; the repo already lists welleng as an owner-reviewed optional adapter |

Without the optional OCR packages the app works fully offline: the Documents tab says "OCR: not
available — OCR engine not installed …", and scanned pages are listed as having no text
(tested). `DRILLMASTER_OCR=0` disables OCR explicitly. No model is downloaded at run time by
this code: `ocr_status()` uses `importlib.util.find_spec` only, and the adapter uses the
models bundled in the wheel.

Model download/installation steps (owner, optional):
`pip install -r requirements-optional.txt` (or `pip install rapidocr==3.10.0 onnxruntime==1.31.0`).
The wheel contains the default models; no separate download step is needed.

## 5. Tests

Environment for all local runs: Linux, Python 3.11.2, PySide6 6.8.1.1,
`QT_QPA_PLATFORM=offscreen`, with a **stub** library directory (`glstub`) providing no-op
GL/EGL/xkbcommon/dbus symbols so Qt can load headless. This is **offscreen Qt with stubbed
system libraries, not native Windows desktop testing.**

Full suite command:
`LD_LIBRARY_PATH=<glstub> QT_QPA_PLATFORM=offscreen python -m pytest -p no:cacheprovider --tb=short -rfE --continue-on-collection-errors`

| Run | Tree | Passed | Failed | Skipped |
|---|---|---|---|---|
| Baseline | `fe04c00` | 2966 | 0 | 4 |
| Mid-mission | M44 edits before the System-panel fix | 3027 | 1 (real defect, fixed in `53a1aa9`) | 4 |
| Package C pre-allowlist | worktree = `53a1aa9` + package C | 3072 | 1 (`test_privacy_check`: screenshots not allowlisted; same as CI) | 4 |
| **Final** | **`23a2bc2`** (clean tree; `f939fbe` changes only the Windows workflow file) | **3074** | **0** | **4** |

New M44 test files (all pass in the final run):

| File | Tests | Mutation check (`old→new` source mutants, one at a time) |
|---|---|---|
| `tests/test_well_trajectory.py` | 30 | 12/12 killed |
| `tests/test_operations_dashboard.py` | 8 | 11/11 killed |
| `tests/test_m44_ui.py` (offscreen widgets) | 21 | 17/17 killed (after strengthening) |
| `tests/test_session_user.py` | 3 | auto-login revert killed |
| `tests/test_document_library.py` | 38 | 16/16 killed |
| `tests/test_documents_tab.py` (offscreen widgets) | 7 | 4/4 killed |
| `tests/test_import_batch_isolation.py` (offscreen) | 1 | 4/4 killed (1 survivor first; test fixed) |

OCR in tests uses a **fake engine object** (`recognize(bytes) -> (text, score)`); the real
RapidOCR adapter is covered by unit tests for absence handling and box-to-line regrouping, and
by the manual end-to-end run in section 4. Persistence in the batch-isolation test is a
**recorder** (atomicity is covered by the existing import-service tests).

Gates on the final tree: ruff E722/F821 = 0; lint debt 749 ≤ ceiling 749 (lowered from 750 in
`53a1aa9`, a real drop); silent-exception scan `silent_unexplained` 83 ≤ ceiling 83; privacy
check 0 findings over the tracked population; coverage floor 45.5 enforced by CI.

## 6. Engineering correctness

* **Defect found and fixed:** survey derived fields are stored per (well, report) frame, each
  restarting at N = E = 0, and later reports repeat earlier stations. Well-scope consumers
  (EOWR, professional export, REST) mixed those frames. Example on synthetic well SYN-DEV-01 at
  MD 1800 m: the stored per-report row gives TVD 1378.88 m / HD 192.84 m; the composed
  whole-well path gives TVD 1612.06 m / VS 586.74 m (61 stations from 66 rows; VS azimuth 135°).
* **Independent check** (closed form, not the implementation): vertical to 600 m, build at
  R = 859.44 m to 40°, hold 600 m gives TVD 1612.06 m and displacement 586.74 m at MD 1800 m;
  a separate golden J-profile (R = 572.96 m) gives TVD 1146.29 m and E 226.76 m at MD 1200 m.
* **Invalid data is never drawn as a valid path:** a missing or invalid angle excludes the
  station (warning); readings that disagree at the same MD are all excluded until reviewed
  (error, REVIEW_REQUIRED); fewer than 2 usable stations gives INSUFFICIENT_DATA with no plot.
  Gaps over 150 m are flagged. Synthetic SYN-QA-03 shows REVIEW_REQUIRED (2 stations from 5 rows).
* **Units and signs:** N/E metres relative to the tie-on (true north up); VS projected on an
  explicit azimuth shown on the axis; DLS °/30 m, converted to °/100 ft by × 30.48/30. The old
  2D side view plotted HD vs TVD and was labelled as a side view; the new viewer plots VS.
* **Tie-on assumption** (first station: N = E = 0, TVD = MD·cos inc, the engine's existing
  behaviour) is shown as an info item. No new formula was introduced; minimum curvature is the
  existing engine. **No ISCWSA error model and no positional uncertainty**; this is plotting
  of reported surveys, not a validated survey-management tool.

## 7. UI paths, screenshots, environment

Screenshots are in `docs/mission-reports/m44-screenshots/`, captured from the real running
`MainWindow` by `tools/screenshots/capture_m44.py`. Capture setup:
- a throw-away synthetic DB, real login path;
- Linux, `QT_QPA_PLATFORM=offscreen`, glstub;
- 1600×1000, Python 3.11.2, PySide6 6.8.1.1.

Each image was reviewed and is pinned by SHA-256 in `tools/privacy/policy.json`. These are
offscreen renders, not Windows desktop captures.

| Before (`fe04c00`) | After (M44) |
|---|---|
| `before_home_dashboard.png`: the old Home tab. In `fe04c00` source, "Last Backup" was always yesterday's date (commented "simulated"), "Active Users" was hard-coded to 1, auto-save always showed "Active", and a failed query displayed "0 today" | `after_home_dashboard.png`: Home → Operations Dashboard |
| `before_trajectory_plot_plan.png`, `before_trajectory_plot_side.png`: the old per-report plot tab, blank as captured in this environment | `after_trajectory_viewer_plan.png`, `after_trajectory_viewer_vertical_section.png` (station selected at MD 1800 m), `after_trajectory_viewer_review_required.png` |
| — | `after_home_drilldown_trajectory_qa.png`: QA flag → viewer |
| — | `after_documents_empty.png`, `after_documents_review_dialog.png` (corrupt file blocked, textless page not approvable), `after_documents_search_source.png` (FTS5 hits with file/location; source page with highlighted terms; Persian cp1256 text) |

## 8. Data health and security

* **No synthetic data in the operational DB:** all fixtures and screenshots use temporary
  databases; the document tests generate files under pytest temp dirs. No real DDR, sample
  file from history or real identifier was used.
* **Authorization at the service boundary:** `documents` and `document_pages` write/delete
  require `can_import`, enforced by the data-layer guard. Tested: a viewer is denied with no
  rows written; an engineer is allowed, with `imported_by` and the audit username recorded.
  The UI button state is cosmetic only.
* **Raw SQL:** the only raw `INSERT` added writes to the library's private `sqlite3
  ":memory:"` FTS index. It was reviewed and added to the raw-DML allowlist with that
  justification; it never touches the application DB.
* **Audit:** a `document_import` record (source pages, stored/skipped pages with reasons,
  edited pages, approved OCR pages, extraction status, encoding) is written in the same
  transaction as the rows. `document_delete` is audited too. A failure mid-import rolls back
  document, pages and audit together (tested by injecting an audit failure).
* **Duplicates:** refused by content SHA-256, even under another file name.
* **Threading:** document extraction workers never open a DB session; all writes happen on the
  UI thread through the existing session factory. The dashboard snapshot runs in
  `ReadOnlyQueryWorker` with its own read-only SQLite connection, so no session is shared
  across threads.
* **M43 behaviours preserved:** the full suite passes, including the migration, rollback,
  audit, double-click, same-date, batch-isolation, permission and worker-safety suites.

## 9. Limitations

* **No 3D in the new viewer.** The old 3D tab is unchanged. PyVista was not added.
* **OCR** has been verified only on synthetic rendered text in an isolated venv. It is not
  bundled, and it is not tested on real scanned DDRs (none may be used). Engine scores are not
  probabilities.
* **Search** is lexical (FTS5, unicode61 tokenizer with diacritics removed, prefix match), not
  semantic. Persian works for exact and prefix tokens; there is no stemming, and no
  normalisation of Arabic and Persian letter variants (ي vs ی, ك vs ک).
* The FTS index is rebuilt in memory when the stored text changes (count/max id/length
  signature). This is suitable for the configured limits (50 MB per file, 500 pages); a
  persistent FTS table was not added, because the schema-equivalence invariant forbids
  untracked tables.
* Documents are library-wide; there is no link to wells or reports yet.
* Limits: 50 MB per file, 500 pages per file, 10 characters minimum per page, text files
  split into 80-line sections, OCR rendering at 200 DPI.
* The `_show_selected_well` signal connection is not covered by a mutation-killing test.
* All UI testing is offscreen on Linux. Windows CI runs the test suite but is not desktop
  acceptance.

## 10. Git

| Item | Value |
|---|---|
| Branch | `arena/72010272-drill-master` |
| Base SHA | `fe04c00bae22b3a839fa1d47ae437d670c93980d` |
| Final code SHA | `f939fbe018f2426329c52dc43cdd39029ddd8f48` |
| Final report SHA | recorded in the closing message (a commit cannot contain its own SHA) |
| Local = remote after code push | yes: `git rev-parse HEAD` = `git ls-remote` = `f939fbe018f2426329c52dc43cdd39029ddd8f48` |
| Worktree at code tip | clean; no untracked files; no unpushed commits |

Recovery note: a sandbox reset during the mission moved the local branch ref back to
`4336ea3` while the worktree kept all files. It was recovered non-destructively: fetch,
temporary-index comparison (worktree = remote tip plus the uncommitted package), CAS
`update-ref`, `read-tree`. No reset, force-push or history rewrite was used. `drill-Master`
and `main` were not touched; nothing was merged, tagged or signed.

## 11. Exact-SHA CI

Code tip `f939fbe018f2426329c52dc43cdd39029ddd8f48` (head_sha equality checked via the
GitHub REST API `actions/runs?head_sha=…`):

| Workflow | Run id | Event | Result | Evidence |
|---|---|---|---|---|
| Source release gate | 40096544909 | push | **success** | jobs source (3.11), (3.12), (3.13) all success; 3.12 leg: product coverage 49.45% (37062/74951, 194 files), floor 45.50% |
| Windows release validation | 40096544907 | push | **success** | job `windows-release` on windows-2022, Python 3.12.10, `QT_QPA_PLATFORM=offscreen`; its pytest step throws on any non-zero pytest exit, and from this SHA it includes the five M44 modules. The installer this pre-existing workflow builds is reported **UNSIGNED** by the job |

Per-test counts for the green runs are written only to the job summary and logs; those (and
the artifact blob host) are not reachable from this environment, so no count is claimed for
them. The last available annotated counts are from the failed `53a1aa9` source legs:
collected 3032, passed 3027, failed 1, skipped 4.

Intermediate SHAs:

| SHA | Source release gate | Windows release validation |
|---|---|---|
| `53a1aa9` | **failure** (run 40077525006; 1 failed: privacy allowlist) | success (40077524811) |
| `97676ce` | success (40095285519) | success (40095285610) |
| `e09fccf`, `23a2bc2` | 0 runs (same push as `f939fbe`; GitHub ran the head only, whose tree contains both) | 0 runs |

The report commit's own CI is recorded in the closing message, because a report cannot
contain the result of the run that tests it.

`53a1aa9` failed its source gate in CI (1 failure: `test_privacy_check`, eight new
screenshots not allowlisted). My local full run had happened before those PNGs were tracked,
so it could not see the failure. The fix is `97676ce`, after a per-image review. The
cancelled/earlier runs of other SHAs are not counted.

## 12. Release readiness (evidence only)

* Final code tree: full suite 3074 passed / 0 failed / 4 skipped (offscreen, stubbed libs);
  exact-SHA CI as in section 11.
* Installer **UNSIGNED**. No EXE, installer or bundle built in M44. No release tag.
* Not established: Windows desktop/operator acceptance, field validation, OCR on real scans,
  owner review of the OCR model licence and of existing dependency licences, history purge.

### Remaining items

**Agent can continue:**
* Link documents to wells and reports (an optional FK plus a filter), and show document hits
  in the dashboard.
* Normalise Arabic/Persian letter variants for search (index and query).
* Add a 3D view in the new viewer once a stable offscreen and Windows test path exists.
* Add a mutation-killing test for the status-bar `_show_selected_well` connection.

**Owner action:**
* Decide whether to adopt optional OCR, and verify the PP-OCR model licence bundled in
  `rapidocr` 3.10.0.
* Decide licence status for PyMuPDF (AGPL/commercial) and other dependencies.
* Windows desktop acceptance of the Home, Trajectory and Documents tabs on real hardware.
* Remaining M43 owner gates (signing, release tag, history purge, containment PR merge).
