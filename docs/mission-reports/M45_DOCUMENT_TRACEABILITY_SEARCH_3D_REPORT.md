# M45 — Document-to-well traceability, Persian/Arabic search normalisation and 3D survey view

Mission M45, branch `arena/72010272-drill-master`, base and start
`0822a28f487ba6a5d9d0c79afbfba18fef378461` (M44 report tip). Written 2026-10-25.
Repository documentation is English. Every number below comes from a command
run in this mission; anything not executed is marked as such.

## 1. Final status

**COMPLETE (code), OWNER_GATED (release).** All three capabilities are
delivered as wired, tested product behaviour:

1. user-confirmed links from library documents to wells and daily reports,
   visible and openable from the Well Info and Daily Report pages;
2. Persian/Arabic-normalised offline search (FTS5), with stored text shown
   exactly as stored and a controlled rebuild for older documents;
3. an interactive in-app 3D survey view built from the same composed
   stations as the 2D Plan and Vertical Section views.

The installer built by the pre-existing Windows workflow is **UNSIGNED**.
Nothing here claims release readiness, Windows desktop/operator acceptance or
field validation; offscreen Qt runs and CI runners are not Windows acceptance.

| Item | Value |
|---|---|
| Base / start SHA | `0822a28` (local clone was found at `4336ea3`; recovered non-destructively, see §11) |
| M45 commits | `d52fbd9` core links + normalised search · `7202352` UI links, related documents, status bar · `595e988` 3D view · `1b8e323` stale link message fix · `f0aee32` 3D canvas margins · `c113cc1` Windows gate list · `087500a` screenshots, capture tool, privacy pins · `780880f` fixture principal isolation · `89a7833` owned 3D draw timer · `27c5ad5` deterministic 3D viewer disposal in tests · `f933081` Matplotlib redraw requests routed through the owned timer |
| Code tip | `f933081fa9a50b91b7ef3716d44f1a3e110587ba` (exact-SHA CI green, §10) |
| Diff base → code tip | 32 files, +3547 / −76 |
| New dependencies | none |

## 2. Recovery and real defects found

On recovery the baseline full suite at `0822a28` was **3074 passed,
0 failed, 4 skipped**. A document was traced from import (worker extraction →
review dialog → atomic import with `document_import` audit) to the source
view (search hit → stored page with highlights). Real defects found and fixed:

1. **No document ↔ well/report relation existed.** Documents could be found
   but not attributed. Fixed by `document_links` (§3).
2. **Arabic and Persian letter forms did not match.** `ي`/`ی` and `ك`/`ک`
   are different code points, so a Persian-keyboard query missed text typed
   on an Arabic layout and vice versa; Persian digits missed ASCII digits.
   Fixed by `core/search_normalization.py` (§4).
3. **Status-bar well label could go stale.** It was updated only by some
   selection paths. Now one handler (`main_window._show_selected_well` /
   `_show_no_selected_well`) follows the selection manager. Texts:
   "🛢️ No well selected", "🛢️ Well: <name>", "🛢️ Well: id <id>".
4. Found while capturing screenshots: the Documents tab kept the message
   "Document linked." after another document was opened (`1b8e323`).

Defects found in M45's own work during verification (fixed, kept in history):

5. **Test isolation** (`780880f`). The Source gate at `d52fbd9` had 9 setup
   errors. Older modules leave the process-wide `permissions` user set; with
   an in-memory database that user id fails the mandatory audit's foreign
   key, so the fixture imports correctly roll back. The M45 fixtures now run
   under `without_session_user()` and restore the previous principal.
   Reproduced by running `test_p0_permissions` (or `test_m29_planning_ui` +
   `test_m28_finance_safety_plan`) first: 38 errors before, 0 after. The
   leaking older modules are unchanged (pre-existing; listed in §8).
6. **Queued 3D draw outliving its canvas** (`89a7833`). Matplotlib's
   `draw_idle` posts an unowned `QTimer.singleShot`. A viewer destroyed
   before the event loop ran left it pending, and the next `processEvents`
   raised `Internal C++ object (FigureCanvasQTAgg) already deleted` — in the
   full local run and in the Source gate at `780880f`, inside the unrelated
   `test_w13_ecd_chart_fallback`. The view now draws through a single-shot
   timer it owns (destroyed with it), and only while visible; a hidden view
   draws when shown.
7. **Windows gate crash at `780880f`**: "Windows fatal exception: stack
   overflow" (native; Python stack 39 frames, no Matplotlib or M45 frame) in
   `app.processEvents()` while setting up the *second* 3D viewer fixture.
   The run artifact host is unreachable from the agent sandbox, so no native
   stack was available. **Probable cause (not proven):** the first viewer,
   kept alive by signal reference cycles, was destroyed by the garbage
   collector at an arbitrary point during Qt event dispatch while an unowned
   Matplotlib draw was still queued. Remedies: the owned timer (item 6) and
   deterministic disposal in the tests (`27c5ad5`: close → `deleteLater` →
   flush deferred deletes). On `27c5ad5` the crash was gone, but three 3D
   tests failed on teardown with the same "already deleted" error raised
   from Matplotlib's *own* `resizeEvent` → `draw_idle` (Windows delivers
   extra resize events). `f933081` routes this canvas's `draw_idle` — used by
   Matplotlib's resize and mouse-rotation handlers — through the owned timer,
   so no redraw request of the 3D canvas can outlive it. The new test
   `test_matplotlib_redraw_requests_cannot_outlive_the_canvas` reproduces the
   Windows error on Linux (same `backend_qt.py:495` frame) when the routing
   is removed. Windows gate at `f933081`: success (§10).

## 3. Document ↔ well/report links

### Capabilities and UI paths

| Capability | Where in the UI |
|---|---|
| Link a stored document to a well, optionally to one of its daily reports, with an optional anchor page | `📄 Documents` → select a document → `Link to well / report…` |
| Link status ("Not linked" or the list of targets) | `📄 Documents` → link panel under the document |
| Change / remove a link | `📄 Documents` → select a link → `Change link…` / `Remove link` |
| Unlinked documents | `📄 Documents` → unlinked filter |
| Linked documents of a well (well-level and report-level links) | `🛢️ Well Info` → `📎 Related documents` → `Open document` |
| Linked documents of a report | `📅 Daily Report` → `📎 Related documents` → `Open document` |
| Open at the anchor page / matched line | `main_window.open_library_document(document_id, page_no)` → Documents tab viewer |

The link dialog (`tabs/document_link_dialog.py`) lists wells with id, name,
code, field and status, and a well's reports with id, date and report number,
so same-name wells and reports are distinguishable. Wells whose name or code
occurs in the stored text are shown as **suggestions only**, with the page
they were found on (whole-token matches, at least 3 characters, never
numeric-only). Nothing is selected until the user picks a row, and the OK
button (`Link` / `Save change`) stays disabled until a well is chosen.
Cancelling changes nothing ("Link cancelled; nothing was changed.").

### Data model and migration

The existing schema had no relation to reuse (`documents`/`document_pages`
came from M44; `wells` and `daily_reports` are unchanged), so one table was
added: `document_links`:

| Column | Type | Rule |
|---|---|---|
| `id` | integer PK | |
| `document_id` | FK `documents.id` | NOT NULL, ON DELETE CASCADE; ORM cascade from `Document.links` |
| `well_id` | FK `wells.id` | NOT NULL, ON DELETE CASCADE |
| `report_id` | FK `daily_reports.id` | NULL = well-level link; ON DELETE CASCADE |
| `page_no` | integer | optional anchor page; must be a stored page of the document |
| `note` | varchar(200) | |
| `linked_at`, `linked_by` | datetime, varchar(100) | |

Constraints: `uq_document_links_target (document_id, well_id, report_id)`
plus the partial unique index `uq_document_links_well_level (document_id,
well_id) WHERE report_id IS NULL` (SQLite treats NULLs as distinct in UNIQUE
constraints). Secondary indexes `ix_document_links_well_id` and
`ix_document_links_report_id` are registered in `core/schema_indexes.py`
(`WELL_SCOPE` / `REPORT_CHILD`). The data-layer policy is
`document_links: write=can_import, delete=can_import | delete_reports | delete_well`.

**Migration.** Additive only. The schema version stays **6**, so older builds
still open the database. An M44 database gains the table and indexes on the
next start without losing documents
(`test_existing_database_gains_the_link_table_without_losing_documents`).
**Rollback check (executed earlier in this mission):** the M44 code (`0822a28`,
temporary worktree since removed) opened a database written by M45 and listed
4 documents with 4 search hits. Deleting a report, then a well, reduced the
links 3 → 2 → 1 via the cascades, with 0 orphans. The scratch evidence directory
lived outside the repository and was lost in a later sandbox reset; the
numbers are those recorded when the check ran.

### Integrity

`core/document_links.DocumentLinkService` runs each create/change/remove as
**one transaction**:

* the document, well and report must exist; the report must belong to the
  well (also enforced by the existing ownership guard in `core/database.py`);
* an anchor page must be a stored page;
* duplicates are refused by the service and by the schema;
* a mandatory audit row is written in the same transaction
  (`document_link`, `document_link_change` with before/after, `document_unlink`).
  An audit failure rolls the change back and is reported as `audit_failed`;
* error codes: `document_missing`, `well_missing`, `report_missing`,
  `report_well_mismatch`, `page_missing`, `duplicate`, `link_missing`,
  `unchanged`, `denied`, `audit_failed`, `failed`.

Deletion follows the current policy, unchanged. Links leave with their
document (counted as `links_removed` in the `document_delete` audit), their
well (inside the audited well delete) or their report (the report-child sweep
of the audited report delete). A link operation never deletes a document.
Extracted text, file name, import review decisions and duplicate-document
prevention (SHA-256) are untouched.

## 4. Persian/Arabic search normalisation

`core/search_normalization.py`, `NORMALIZATION_VERSION = 1`. Normalisation is
applied **only** to the in-memory FTS5 index and to queries, the same way on
both sides:

| Input | Indexed / compared as |
|---|---|
| Arabic yeh U+064A, alef maksura U+0649 | Persian yeh U+06CC |
| Arabic kaf U+0643 | Persian keheh U+06A9 |
| Arabic-Indic and Persian digits | ASCII digits |
| ZWNJ U+200C (half-space) | removed; a space typed where the document has a half-space is handled by an extra joined alternative at query time |
| harakat U+064B–065F, superscript alef U+0670, tatweel U+0640 | removed |

Deliberately **not** merged, because each would join distinct words: alef forms
(آ/أ/إ/ا), teh marbuta/heh (ة/ه), hamza seats; no stemming. Repeated spaces
and line breaks never matter, because the tokenizer splits on whitespace.
Phrases, numbers, identifiers such as `SYN-07` and English words keep working.
The last token of a phrase gets no prefix `*`, because that produced false
matches.

**Originals stay intact.** Each match in normalised text is mapped back to a
character span of the stored text (`normalize_with_map` / `find_spans`).
Snippets, highlights and the opened page therefore show the original exactly
as stored, with the page and line of the first match. Stored page text is
never rewritten.

**Old documents.** The normalisation version is part of the index signature,
so documents imported before the change are re-indexed from their stored
originals on the next search. `📄 Documents` → `Rebuild index` forces it and
reports the page count and version. The substring fallback (no FTS5) uses the
same normalisation. Measured: on an index built before normalisation, 1 of 2
synthetic documents was found; after the rebuild, 2 of 2.

Synthetic fixtures (`tests/test_search_normalization.py`, offline): an
Arabic-letter document found with Persian forms and the reverse; a half-space
word typed three ways; a multi-word phrase with a well id and a number; English
inside Persian text; empty and unmatched queries; precision checks (unrelated
documents not returned); hits showing original text and location; an old index
before the rebuild; fallback parity. UI: a search result opens the original
text at the match (`test_search_result_opens_the_original_text_at_the_match`).

## 5. 3D survey view

**Where:** `📍 Trajectory` → `Well Trajectory Viewer` → `3D view` tab, next
to `Plan view` and `Vertical section`, which remain the 2D reference.

* **Same data, no new formula.** `core/trajectory_3d.scene_from_trajectory`
  re-labels the stations computed by the existing
  `core.well_trajectory.compose_well_trajectory` (minimum curvature), with
  the same display-unit conversion (`to_display_units`):
  `x = East, y = North (relative to the tie-on), z = TVD positive down`
  (axis drawn inverted). Units are those of the 2D views (m or international ft).
* **Controls:** drag to rotate, wheel or `Zoom +` / `Zoom −`, view presets,
  `Reset view`, equal-scale toggle (on by default; off is labelled "angles
  distorted"), orthographic projection. A click on a station selects the
  **real** station everywhere: the selected-station panel and the stations
  table show MD, inc, azi, TVD, N/E, VS and DLS, and the table selection
  highlights it in 3D.
* **Invalid data never looks valid.** A scene exists only for a drawable
  trajectory (at least 2 computed stations, READY or REVIEW_REQUIRED).
  Excluded, duplicate-depth or invalid rows are not stations and never become
  points; out-of-order stations are refused, not reordered. A single station,
  no survey or an insufficient one shows its reason and draws nothing.
* **Graceful disabling.** Without an interactive Qt canvas, the tab says
  "3D view unavailable — <reason>". A static Agg fallback is reported as not
  interactive and never presented as 3D.
* The 3D view never writes engineering values.

### Library evaluation

| Option | Version | Licence | Result |
|---|---|---|---|
| Matplotlib `mplot3d` (**chosen**) | 3.9.3, already in `requirements-lock.txt` | Matplotlib License (PSF-based, BSD-compatible); locked dependencies: numpy BSD, pillow MIT-CMU, kiwisolver BSD, cycler BSD, fonttools MIT, pyparsing MIT, contourpy BSD-3, python-dateutil BSD/Apache, packaging Apache/BSD | Uses the existing PySide6 6.8.1.1 (LGPL) `QtAgg` canvas; renders offscreen on Linux; passes the Windows gate on `windows-2022` (§10); no new package and no size increase (the win_amd64 wheel is 7.8 MB and already shipped) |
| PyVista + pyvistaqt over VTK | 0.49.1 / 0.13.1 / VTK 9.5.2 | MIT / MIT / BSD | Rejected: an experiment in this sandbox gave no testable offscreen render (VTK needs a real OpenGL context; only stub GL libraries exist here), and it would add a ~64 MB native wheel (VTK win_amd64) |

Matplotlib's 3D is a projection renderer, not a GPU scene graph; for a single
well path with stations this is sufficient and testable.

## 6. Tests

### New modules (counts from this mission's runs)

| Module | Tests | Covers |
|---|---|---|
| `tests/test_document_links.py` | 23 | link to well and to report, listed per well/report and audited; nonexistent document/well/report/page, report of another well (no row, no audit); duplicates refused by service and schema; ORM ownership guard; audit failure rolls back create/change/remove; change audited with before/after; removal keeps the document; same-name picker; unlinked list; suggestions never link and are whole-token only; report, well and document deletes; data-layer permission; report delete needs only the report-delete permission; migration of an existing database |
| `tests/test_search_normalization.py` | 16 | §4 |
| `tests/test_m45_ui.py` | 14 | dialog suggests but links only after confirmation; cancel changes nothing; same-name wells in the dialog; duplicate, change and remove through the tab; stale link message; unlinked filter; search hit opens the original at the match; rebuild reports pages and version; link buttons follow the role; related-documents panel lists and opens; status-bar label follows selection, well change, view switch, no selection and new selection; deleting the current report leaves no stale well; well page and report page list and open linked documents and follow link changes |
| `tests/test_trajectory_3d.py` | 21 | vertical well (TVD = MD, no lateral drift); build + azimuth turn against independent parametric-circle geometry (within 1e-6 m); exact feet conversion; excluded rows never points; non-drawable states; out-of-order refusal; equal/independent limits; nearest-station picking; UI: 3D data equals 2D plan/section data, click vs drag picking, table → 3D highlight, presets/reset/zoom change only the camera, unit/scale options, no-plot messages, single station, no canvas, static Agg fallback; a destroyed view leaves no pending draw; Matplotlib's own redraw requests cannot outlive the canvas; a hidden view draws when shown |

The geometry goldens are independent of the implementation (closed-form
circle arcs, not the engine).

### Mutation testing of the new contract tests

Scripted source mutants; each must make at least one test fail.

| Area | Killed / total |
|---|---|
| links and schema | 15 / 16 (the survivor is an equivalent mutant) |
| normalisation | 12 / 12 |
| UI workflow | 15 / 15 |
| stale link message | 1 / 1 |
| 3D geometry and view | 22 / 22 |
| owned draw timer, hidden-view draw, Matplotlib redraw routing | 3 / 3 |
| non-reproducing sequence check | 1 survivor (D1b) |

D1b re-ran `test_m44_ui` + `test_w13_ecd_chart_fallback` with the old draw
path. The ordering that exposed item 6 needed the full suite, so the two
modules alone do not reproduce it. The defect itself is pinned by the
dedicated tests above. One 3D test was strengthened after a first survivor (a
rotation drag now ends on a station).

### Results by run type (Linux, offscreen Qt, stubbed GL)

| Run | Result |
|---|---|
| Baseline full suite at `0822a28` | 3074 passed, 0 failed, 4 skipped |
| Related + regression list (new modules, documents, schema indexes, model registry, data-layer authorization, ownership, migration acceptance, M44 UI, w2, import architecture, core import, privacy, selection smoke, well trajectory) | 318 passed, 0 failed |
| Commit `d52fbd9` alone (old UI files) | 214 passed, 0 failed |
| Windows-gate contract test after `c113cc1` | 66 passed |
| Full suite at `087500a` | stopped (test files changed during the run); not counted |
| Full suite at `780880f` | 3144 passed, **1 failed** (`test_w13_ecd_chart_fallback`, item 6), 4 skipped |
| Full suite at `27c5ad5` | 3147 passed, 0 failed, 4 skipped (566.91 s) |
| Windows-gate module list + `test_m45_ui` + `test_m44_ui` + `test_w13_ecd_chart_fallback` at `f933081` | 1021 passed, 0 failed, 1 skipped |
| Full suite at `f933081` | 3148 passed, 0 failed, 4 skipped (564.97 s) |
| Full suite at `f933081`, rebuilt environment after a sandbox reset | 3148 passed, 0 failed, 4 skipped (655.23 s) |
| The four M45 modules, rebuilt environment | 74 passed (23 + 16 + 14 + 21) |

3148 = 3074 baseline + 74 new tests. Gates on the code tip: `ruff` clean on
changed files; `verify_lint()` True; exception scan rc 0 (ceiling unchanged);
privacy check 0 findings over 1051 files.

### What offscreen runs cover and what they do not

The offscreen runs use the real widgets, signals, dialogs and Matplotlib
canvas with raster rendering and synthetic data, and stub GL, EGL, dbus and
xkbcommon libraries (no Qt library is stubbed). They do **not** cover a
native Windows desktop, real mouse rotation feel, GPU rendering, DPI scaling
or fonts. The Windows CI gate runs the three non-window M45 modules (links,
normalisation, 3D) with `QT_QPA_PLATFORM=offscreen` on `windows-2022`.
`test_m45_ui` (full `MainWindow`) is not in the Windows list, consistent with
the other MainWindow UI suites.

## 7. Screenshots

`docs/mission-reports/m45-screenshots/` holds 9 PNGs, each reviewed and
pinned by SHA-256 in `tools/privacy/policy.json`:

| File | Shows |
|---|---|
| `m45_link_dialog_suggestion_unconfirmed.png` | link dialog with a text suggestion; nothing selected |
| `m45_link_dialog_confirmed_choice.png` | after the user chose a well and a report |
| `m45_documents_linked_status.png` | Documents tab with the link status |
| `m45_documents_persian_search.png` | Persian-form query matching Arabic-letter text; original highlighted |
| `m45_well_page_related_documents.png` | Well Info → Related documents |
| `m45_report_page_related_documents.png` | Daily Report → Related documents |
| `m45_trajectory_3d_picked_station.png` | 3D view with a picked station (MD 1350 m: TVD 1267.34, N/E −210.36/210.36, VS 297.49 — synthetic) |
| `m45_trajectory_plan_same_station.png` | the same station in the Plan view |
| `m45_trajectory_3d_top_preset.png` | the top preset |

**Conditions:** the real `MainWindow`, via
`tools/screenshots/capture_m45.py`, against a throw-away synthetic database
(`tests/synthetic_operations.py`) in a temporary directory. Sign-in uses the
real authentication path; synthetic documents go through the real reviewed
import; the link is made through the real dialog. Captured with
`QWidget.grab()` on Linux, `QT_QPA_PLATFORM=offscreen`, Python 3.11.2,
PySide6 6.8.1.1, 1600×1000, stubbed GL. Not a native Windows desktop. The
related-documents panels are scrolled into view within the page's own scroll
area. The top preset looks along the TVD axis, so its labels overlap. Mouse
rotation is not captured.

## 8. Limitations and owner actions

- Native Windows desktop check of the link workflow, the status bar and 3D
  rotation/zoom/picking with a real mouse and GPU (owner).
- The related-documents panels sit at the bottom of the Well Info and Daily
  Report pages; moving them higher is a layout decision.
- The anchor page defaults to the selected search hit's page, not to the
  page being browsed.
- Normalisation does not merge alef variants, `ة`/`ه` or hamza forms (by
  design); no stemming.
- Older test modules still leave the global `permissions` user set
  (`test_import_to_selection_ui_smoke_m25`, `test_inventory_widget_smoke`,
  `test_m28_finance_safety_plan`, `test_m29_planning_ui`,
  `test_p0_permissions`, `test_planning_material_persistence`, partly
  `test_documents_tab`). M45 fixtures are immune; those modules were not
  changed.
- The Windows crash cause in item 7 is probable, not proven (no native
  stack was reachable); the gate is green on the code tip with the 3D module
  still in it.
- Intermediate SHAs `7202352` … `087500a` and `89a7833` have no exact-SHA CI
  runs (pushed together with a later head); no CI result is claimed for them.
- PyMuPDF (AGPL, in the M44 lock) and OCR model licences remain owner
  decisions (out of scope).
- UNSIGNED; no release, tag, installer, EXE or readiness claim from this
  mission.

## 9. Files

Added: `core/document_links.py`, `core/search_normalization.py`,
`core/trajectory_3d.py`, `tabs/document_link_dialog.py`,
`tabs/related_documents.py`, `tabs/trajectory_3d_view.py`,
`tests/document_link_fixtures.py`, `tests/test_document_links.py`,
`tests/test_search_normalization.py`, `tests/test_m45_ui.py`,
`tests/test_trajectory_3d.py`, `tools/screenshots/capture_m45.py`,
9 screenshots.
Changed: `core/database.py`, `core/authorization.py`,
`core/schema_indexes.py`, `core/document_library.py`,
`tabs/documents_tab.py`, `tabs/w1_well_info.py`, `tabs/w2_Daily_Report.py`,
`tabs/trajectory_viewer.py`, `main_window.py`,
`.github/workflows/windows-release-gate.yml` (adds the three non-window M45
modules), `tools/privacy/policy.json`.

## 10. Exact-SHA CI

Code tip `f933081fa9a50b91b7ef3716d44f1a3e110587ba`. `head_sha` equality was
checked with the GitHub REST API (`actions/runs?head_sha=…`):

| Workflow | Run id | Event | Result | Evidence |
|---|---|---|---|---|
| Source release gate | 40170075007 | push | **success** | jobs source (3.11), (3.12), (3.13) all success; 3.12 leg annotation: product coverage (branch+line) 57.11% over 200 tracked files (43643/76423), floor 45.50% (floor unchanged) |
| Windows release validation | 40170074995 | push | **success** | job `windows-release`, Python 3.12.10, offscreen Qt; the pytest list includes `test_document_links`, `test_search_normalization` and `test_trajectory_3d`. The installer this pre-existing workflow builds is reported **UNSIGNED** by the job |

Per-test counts for green runs are written only to job logs and summaries,
which are not reachable from this environment, so no count is claimed for
them.

Intermediate SHAs:

| SHA | Source release gate | Windows release validation |
|---|---|---|
| `d52fbd9` | **failure** (40167058631; 9 setup errors, item 5) | success (40167058553) |
| `7202352` … `087500a` | no runs for these SHAs | no runs |
| `780880f` | **failure** (40168089011; 1 failed, `test_w13_ecd_chart_fallback`, item 6; collected 3149, passed 3144, skipped 4) | **failure** (40168089020; native stack overflow, item 7) |
| `89a7833` | no runs (pushed with `27c5ad5`) | no runs |
| `27c5ad5` | success (40169057878) | **failure** (40169057891; 3 teardown errors, item 7) |
| `f933081` | **success** (40170075007) | **success** (40170074995) |

The report commit's own CI is recorded in the closing message, because a
report cannot contain the result of the run that tests it.

## 11. Git state

* Start: remote branch at `0822a28`. The local clone was at `4336ea3` and was
  recovered by fetch and comparison, with no reset.
* During the mission a sandbox reset returned the local clone to `4336ea3`,
  with the working tree restored from the snapshot. The working tree was
  verified **identical** to `f933081` (temporary index, tree
  `21ce389e10fa83e86fe1eb6f41549dc7421dbbf8` on both sides). The branch ref
  was then moved with a compare-and-swap `update-ref` (old value `4336ea3`)
  and the index rebuilt from HEAD; no file was changed. Out-of-repository
  scratch files (logs, report draft, mutation script, rollback evidence)
  were lost; this report was rewritten from the repository and the recorded
  results.
* No force-push, reset, rebase or history rewrite. Only
  `arena/72010272-drill-master` was pushed; every push was confirmed with
  `git ls-remote`.
* Code tip `f933081`; report tip = the commit adding this file (see the
  closing message); worktree clean with local = remote at the end.
