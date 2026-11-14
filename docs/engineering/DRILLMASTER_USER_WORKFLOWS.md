# DrillMaster user workflows (M53–M60, extended through M96)

Step-by-step workflows for the product capabilities added or completed in M53–M60. Screen names are those shown in the application.

The Home/Operations dashboard is English-only and left-to-right. The other screens keep their existing English/Persian localization.

Automated evidence for these workflows comes from offscreen Qt tests on Linux with synthetic data. That is **not** Windows desktop acceptance, which remains an owner item.

## 1. Portfolio overview (Home dashboard, M53)

1. Open **Home**. The dashboard loads in a background worker. A loading state is shown, and a result for an outdated filter is discarded.
2. Narrow the scope with the filter bar: company, project, well, rig, status and period. Every KPI card, chart, alert, the portfolio table and recent activity update together.
3. Hover over a KPI card to see its definition, unit, source and freshness. A KPI without data shows **Unavailable**; it never shows zero.
4. Click a well in **Portfolio**, an alert in **Attention**, or a row in **Recent activity** to open that well, report or tab.
5. **Trajectory preview** is drawn only from saved survey stations. **Open full view** opens the trajectory viewer.

## 2. Daily drilling report (W2, M54)

1. Select a well. The **Report timeline** lists its reports oldest first and marks the open one.
2. Open a report with a timeline double-click, or with **Previous** / **Next**. If the open report has unsaved edits, you must confirm before they are discarded.
   * Display-only panels, such as related documents or the timeline itself, do not count as edits.
3. **New report** starts an empty draft.
4. **Duplicate for review** opens a review dialog:
   * choose the new date and number;
   * optionally copy the time log.

   The draft is **not saved** until you press Save. A warning appears if a report already exists on that date.
5. **Save** validates the time logs:
   * overlapping intervals block the save and name both rows;
   * gaps are reported as notes;
   * an unreadable time names its row.

## 3. Importing a DDR file (Excel/PDF, M54)

1. Use **Import** in the daily report area and choose an Excel or PDF file.
2. Optional: choose a **Report profile** for the operator or format, or create one from **Profiles…**. Profiles are versioned; saving creates a new version and never overwrites the old one.
3. PDF pages without a text layer are reported as scanned. **OCR unavailable** is shown, because no local OCR engine is installed. Continued and wrapped tables are joined. Page headers and footers are excluded.
4. Review every proposed field in the review workspace. Each field shows:
   * source page or cell;
   * original and normalized value;
   * unit;
   * mapping;
   * confidence;
   * warning and decision.

   The selected row's full detail appears in the detail panel. Edit or reject values as needed.
5. Confirm. Only confirmed values are written. Nothing is saved silently, and the suggested well match is only a suggestion.

## 4. Importing surveys (W6 Trajectory → Survey Data, M55)

1. Select the well and report, then press **Import** on the survey table.
2. Choose a CSV, TXT, DAT or XLSX file. For a workbook, pick the sheet.
3. In the import dialog:
   * Confirm the **depth unit**. If the column header does not state it, you must choose metres or feet. A conflict between the header and your choice blocks the import.
   * State the **azimuth reference** (true, grid or magnetic north, or "not stated"). It is recorded as stated and not converted.
   * Review accepted stations (MD shown in metres) and rejected rows with their source row and reason.
4. Press **Import N station(s)**. The survey table is filled, and a message states that nothing is saved yet.
5. Press **Save** to persist the surveys. Saving replaces the surveys of the current well/report scope and runs the canonical validation again.

## 5. Designing a well plan (Trajectory viewer → Plan designer, M55)

1. Open the trajectory viewer and the **Plan designer** tab.
2. Add segments:
   * **Hold** (length);
   * **Curve** (target inclination, azimuth and DLS in deg/30 m). Build, drop and turn are named automatically;
   * **Hold to TVD**.
3. Optional:
   * a **DLS limit** (0 means no limit). A breach is warned, never clipped;
   * a vertical-section azimuth and a station step;
   * targets (north, east, TVD, radius).
4. Press **Design**. The summary lists:
   * end-of-section MD and TVD;
   * maximum DLS;
   * warnings;
   * the closest approach to each target and whether it falls inside the radius.
5. **Export CSV** writes the stations with a header stating the method and "planning aid, not an approved plan".
6. **Use as plan for comparison** hands the stations to **Compare / clearance** in plan-vs-actual mode and switches to that tab.

## 6. Plan vs actual and offset screening (Trajectory viewer → Compare / clearance, M52/M55)

1. Plan mode: load a plan file (CSV/TXT/XLSX, with the MD unit) or use a designed plan. Press **Compare**.
2. The table shows, per actual station:
   * plan MD;
   * distance;
   * high/low and right/left deviation;
   * along-hole difference.
3. **Save** writes a new comparison record (append-only). **Export CSV** writes the table.
4. Offset mode: choose an offset well and confirm both wells share a CRS. The result is **SCREENING — NO ISCWSA UNCERTAINTY — NOT APPROVED (centre-to-centre)**. Separation factor and ellipse clearance are not offered, because no uncertainty model is available.

## 7. Engineering calculators (W13)

1. Open **Engineering Calculator**. The calculators are grouped in tabs: volume, hydraulics, bit hydraulics, weight, stuck pipe, mud, casing/cement, well control, directional, fishing and the drill-pipe database.
2. Results that have a canonical engine show the method and warnings. Casing, cement, torque and drag, MSE and kill-sheet results are stored as calculation records. MSE has a history browser.
3. The status of each calculator (complete, screening, partial) is listed in `PRODUCT_CAPABILITY_MATRIX.md`.

## 8. Batch DDR import with a report profile (M61)

1. Daily Report → Import, choose the report profile, then select one or more files.
2. The **batch queue** lists every file with its status (QUEUED, RUNNING, SAVED, REVIEW_REQUIRED, SKIPPED, DUPLICATE, FAILED, CANCELLED), stage, profile, attempts and last diagnostic.
3. Each file opens its own preview. The header shows the profile threshold and how many values are eligible, need review, are low or are not scored. *Accept all high confidence* uses the profile threshold and never accepts a value that still needs review (for example an ambiguous date).
4. Rows ignored by the profile's stop/skip rules appear as review items with the rule and page/row.
5. **Remove selected** drops a queued/failed/skipped/cancelled/duplicate file; **Retry failed** re-runs failed, skipped and cancelled files; **Cancel remaining** cancels files that have not started (the running file finishes atomically).

## 9. Saving and revising a directional plan (M62)

1. Trajectory viewer → Plan designer, with a well selected. Design the plan.
2. **Save as new plan…** stores revision 1. After changes, **Save revision** stores revision 2 with a link to its parent; revision 1 is unchanged.
3. Pick any saved revision and **Open** (redesigned with the current designer; a version difference is noted), **Clone…** (new plan), **Archive**, or **Compare with open** (input differences and TD/TVD/max DLS/end-point deltas).
4. The **Plots** tab shows Inc, Azi, DLS and TVD vs MD. Target results give the continuous closest approach on the arc and the closest station.

## 10. Calculation cases in W13 (M63)

1. Open a calculator, calculate, then **Save case…** under the finder.
2. Choose a saved case: **Reopen** restores its inputs (and shows the stored results), **Compare with current** lists differing inputs/results, **Re-run & save** recalculates and stores a new child case. Stored cases are never edited.

## 11. Calculation history and reports (M67)

1. Open **Calc History**. It follows the selected well (clear *Selected well only* for all wells); filter by source or text.
2. Select one entry to see its report; select two and **Compare selected (2)**.
3. **Recalculate & verify** re-runs an engine snapshot or plan with the current method and reports MATCH / DIFFERENT / NOT_REPRODUCIBLE / UNREADABLE and whether the method changed. **Save recalculation** stores it as a new case; the original is untouched.
4. **Export report…** writes HTML or PDF (UNSIGNED, not validated); **Export list CSV…** writes the filtered list.

## 12. Survey revisions and tied plans (M72)

Trajectory viewer -> **Survey revisions**: declare the depth datum (and the unit for a file), then *Freeze
current survey* or *Import station file…* -> *Save previewed revision*. Each revision is numbered and cannot
be edited; *Compare with parent* lists the differences. In the **Plan designer**, choose the survey revision
station to tie in to, add a target and *Solve to first target*; an infeasible target shows the reason.
*Use as plan for comparison* hands the plan, prefixed with the surveyed stations above the tie-in, to
Compare / clearance, where the actual source can be a survey revision.

## 13. Well architecture and cement worksheet (M74)

W3b Wellbore schematic -> **Architecture**: build the drawing in the Casings / Formations / Completion tabs,
*Validate drawing*, then *Freeze as revision* (optionally against a survey revision). *Load into schematic*
redraws a stored revision. Select a revision and a cemented string, enter the open-hole size if it is not
recorded, *Cement annulus*, then *Save worksheet* to store it as a calculation case.

## 14. Operational analysis (W12 → Operational analysis, M91)

1. Select a well (optionally a wellbore and a date range). The scope line names the well and wellbore,
   e.g. "SYN-ALPHA-01 (well #2) (whole well)".
2. **Refresh** builds daily footage, drilling hours, ROP, NPT, activity, bit-run, MSE and cost tables from the
   stored reports. Cells that are unknown show as missing (never 0); activity rows marked `UNCERTAIN` come
   from fuzzy mapping.
3. Double-click a row that has a source report (or use **Open report**) to open that report in W2
   (drill-down). **Export** writes Excel or CSV with the scope and method metadata.

## 15. Method catalogue (Help → Method catalogue, M92)

Read-only list of every method with status, version, reference, licence, limits and blockers. Approval is an
owner decision outside the application; nothing in the catalogue can be approved from the UI.

## 16. Report export with provenance (W11, M93)

Choose the report, format (HTML, PDF, Excel, CSV) and direction (LTR/RTL), then export. The export runs on a
worker (the window stays responsive). Every output starts with its provenance: scope, sources, revisions,
methods and the unsigned label.

## 17. Deleting a well, section or report (M96)

Deleting a well removes its sections, reports, revisions, calculation cases, saved W13 calculations and other
well-scoped records in one transaction, with one audit entry that lists what was removed. Deleting a section
keeps the well's procedures but clears their section reference. Viewers cannot delete. If anything fails,
nothing is deleted. Saved revisions and cases cannot be edited or deleted on their own.

## 18. Saved trajectory views (Trajectory viewer → Saved views, M178–M180)

The legacy "Trajectory Plot" tab is retired (M180); its saving and export live here. With a well selected:

1. Choose the source: the well's survey stations, or a VERIFIED survey revision.
2. **Save current view…** stores a named view of the stations, the display settings (scope, unit, vertical-section mode and azimuth, station markers, equal scale) and the
   source fingerprint. Names are unique among the well's active views.
3. **Open** shows the stored stations exactly as saved and says whether today's data still match
   (MATCH / DIFFERENT / NOT_REPRODUCIBLE; a damaged snapshot is UNREADABLE and is not drawn).
4. **Revise with current settings…** (a reason is required) adds revision *n + 1*; the old revision stays
   readable. **Clone…** starts a new view from the selected one. **Compare with previous revision** pairs
   stations by MD only (no interpolation). **Archive…** / **Restore…** need a reason.
5. **Export CSV… / JSON…** writes the stored stations in the displayed unit with a header naming the view,
   well, revision, units and snapshot SHA-256. A value the snapshot does not hold is left empty (CSV) or
   `null` (JSON) — never 0.

If anything fails the status line says **NOT SAVED** or **NOT EXPORTED** and nothing is written. If another
user changed the view first, the action is refused; reopen the view and try again. Plot snapshots saved by
the old tab are listed read-only as legacy snapshots.

## 19. Tubular reference library (Tools → Tubular Reference Library, M157, M181–M189)

DrillMaster ships **no** pipe or casing data (no licensed source exists yet; see
`docs/engineering/M181_TUBULAR_SOURCES.md`). You build the library yourself:

1. Click **Import / publish…**, then **New draft set…**. Use **Choose file…** to pick an XLSX, CSV or JSON file
   in the template layout (`docs/engineering/tubular_import_template.csv`). State once where the values
   come from: your own measurement (`user`), or a manufacturer document with its licence. Files citing API / ISO
   tables are refused.
2. **Read the preview.** Each row is NEW, ALREADY_PRESENT, DUPLICATE_IN_FILE, CONFLICT (never overwritten) or
   INVALID (with the reason). Blank cells stay unavailable, never 0.
3. **Confirm and give a reason.** If the file changed after the preview, the set is no longer a draft, or the
   audit record cannot be written, the import says **NOT IMPORTED** and nothing is written.
4. **Publish** the set. A published set is immutable; changes become a new version.
5. **Use an item in a calculation:**
   - Click **Library…** in the drill-string component dialog (Volumes, Hydraulics, Weight / T&D), on the Casing
     Strength page, or under the casing table of the Well Architecture page.
   - Only the values the item holds are filled; the rest stays empty for you to enter.
   - Yield strength and ratings are never filled. A wall derived as (OD − ID)/2 is labelled DERIVED.
6. **What a saved case keeps.** It keeps an immutable snapshot of the item. Editing a filled value removes the
   link; the value then counts as yours.
7. **Reopening a case** shows on the status line whether the library still matches: MATCH, DIFFERENT,
   NOT_REPRODUCIBLE (the set is not in this database) or UNREADABLE. The case keeps its stored values either way;
   nothing is re-read from today's library.
