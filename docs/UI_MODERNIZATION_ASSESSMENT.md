# UI modernization assessment (M43 Phase 7, 2026-10-21)

This document assesses the code and plans the work. Apart from the restore and
autosave fix below, **no UI refactor was performed in M43**. Each item's status
is shown.

## 1. `QApplication.processEvents()`: 22 calls, NOT_RUN (migration)

Every call follows the same pattern: update a status label or log, call
`processEvents()` to repaint, then run blocking work on the GUI thread.

| Area | Calls | Enclosing functions | Blocking work that follows |
|---|---|---|---|
| `app.py` | 3 | `set_status`, `initialize` | splash and start-up initialization |
| `main_window.py` | 2 | `set_message`, `show_loading` | start-up and loading overlay |
| `dialogs/login_dialog.py` | 1 | `authenticate` | bcrypt verification and database lookup |
| `dialogs/excel_import_dialog.py` | 3 | `_unified_import`, `_run_import_pipeline` | per-file routing, extraction, validation |
| `dialogs/smart_template_dialog.py` | 1 | `_smart_auto_detect` | template detection |
| `tabs/w11_Export.py` | 11 | `_export_eowr`, `_export_npt`, `_export_cost`, `_export_plan`, `_export_batch` (7) | PDF/HTML/Excel generation |
| `tabs/w3b_wellbore_schematic_tab.py` | 1 | `auto_generate` | schematic generation |

**Risk:** `processEvents()` re-enters the event loop in the middle of an
operation. Timers (autosave every N minutes, the hierarchy refresh) and queued
clicks can run then. For example, an autosave tick during an Excel import runs
the tab's `save_changes` while the import is half done. Neither `tabs/w11_Export.py` nor
`dialogs/excel_import_dialog.py` calls `setEnabled` at all, so their controls stay
live while `processEvents()` runs.

**Plan (one area per commit):** move the blocking part to the existing
`core/async_workers.FunctionWorker` (a `QThread`), or to the
`MaintenanceWorker` pattern used by backup and restore. That pattern:

- disables the window or its controls;
- pauses autosave (`MainWindow._set_maintenance_mode`);
- refuses close while running;
- delivers the result through a signal on the GUI thread.

Rules:

- **Session ownership:** each worker opens and closes its own SQLAlchemy
  session; no ORM object crosses threads, only plain dicts or ids.
- **Cancel:** cooperative cancellation via a flag checked between files or
  exported sections.
- **Shutdown:** `closeEvent` waits with a timeout, as the backup scheduler does
  (`stop(120)`).

Start with `w11_Export` (11 calls, no database writes) and the import dialog
(highest re-entrancy risk). Login is last: it is short and modal.

## 2. Restore versus autosave: VERIFIED (fixed in M43)

Before the fix, the maintenance path resumed every autosave before the restore
result message was shown. Since `ec12eb2`, once the live database has been
replaced, or its rollback failed, autosave stays off until restart.
`tests/test_db_maintenance_ui.py` checks the timer while the message is open.

## 3. Undo (`QUndoStack`): NOT_RUN (assessment only)

- **Current state:** 0 uses of `QUndoStack`. The daily report and survey editors
  are table widgets saved explicitly or by autosave.
- **Feasible design:**
  - one `QUndoCommand` per committed cell edit and per row insert or delete,
    storing the old and new display values;
  - merge consecutive edits to the same cell (`mergeWith`);
  - one stack per open report or survey;
  - clear the stack on load, report switch and successful restore.
- **Constraints:**
  - Undo must not cross a save boundary silently. After a save, undo edits the
    widget only and marks it dirty; it never rewrites the database directly.
  - Autosave must treat the result of an undo like any other edit.
  - Survey edits invalidate stored trajectory results, so undo must mark them
    stale exactly as a manual edit does.
- **Effort:** medium per editor. Survey first: one table, numeric cells, clear
  invalidation rule.

## 4. Translation (`tr()`): NOT_RUN

- **Current state:** 7 `tr("…")` calls, no `QTranslator`, no `.ts`/`.qm`
  catalog. User-visible strings are inline literals: Persian in some places,
  English in many.
- **Plan:**
  - keep Persian as the default source language where it is the shipped text;
  - wrap strings with `self.tr()` file by file;
  - generate catalogs with `pyside6-lupdate` and load them with a
    `QTranslator` in `app.py`;
  - keep RTL by setting `QApplication.setLayoutDirection(Qt.RightToLeft)` when
    the Persian locale is active.
- A test should ensure each wrapped file still imports and that the catalog
  build is reproducible.

## 5. Theme: NOT_RUN

- **Current state:** 502 `setStyleSheet` calls (excluding tests) and no central
  theme module; `ui/` contains only `helper.py` and `utils.py`.
- **Plan:**
  - add `ui/theme.py` with named tokens (colours, spacing, fonts) and a few
    style helpers;
  - migrate one tab per commit, replacing literal stylesheet strings with
    tokens;
  - pin a stylesheet-count ratchet (like the ruff ceiling) so the number can
    only go down;
  - preserve Persian fonts and RTL alignment. Visual changes need screenshots
    from the official runtime, not the headless stub.
