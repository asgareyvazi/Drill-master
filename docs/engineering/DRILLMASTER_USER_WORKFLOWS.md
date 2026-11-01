# DrillMaster user workflows (M53–M60)

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
4. Offset mode: choose an offset well and confirm both wells share a CRS. The result is **SCREENING – centre-to-centre, no ISCWSA uncertainty, NOT APPROVED**. Separation factor and ellipse clearance are not offered, because no uncertainty model is available.

## 7. Engineering calculators (W13)

1. Open **Engineering Calculator**. The calculators are grouped in tabs: volume, hydraulics, bit hydraulics, weight, stuck pipe, mud, casing/cement, well control, directional, fishing and the drill-pipe database.
2. Results that have a canonical engine show the method and warnings. Casing, cement, torque and drag, MSE and kill-sheet results are stored as calculation records. MSE has a history browser.
3. The status of each calculator (complete, screening, partial) is listed in `PRODUCT_CAPABILITY_MATRIX.md`.
