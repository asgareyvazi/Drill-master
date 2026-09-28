# P6 p6-batch-002 — class A (safety / authorization / mutation)

records **45** over **36** sites · VERIFIED-CORRECT: 24 · INTENTIONAL: 16 · DOMAIN_DECISION_REQUIRED: 3 · DUPLICATE/FALSE-POSITIVE: 2

## INV34-000074 — `core/ai_import_mapper.py:151`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class A)
- **Symbol:** `AIImportMapper._valid_proposal`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** `_valid_proposal` is the predicate of a validity filter; its only caller builds `valid = [p for p in proposals if self._valid_proposal(p, fields)]` (line 131) and every other malformed-field branch in the same function also returns False (lines 144-148). An unparseable confidence makes the proposal invalid - by design, not a swallowed failure.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-000716 — `core/database.py:3488`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `DatabaseManager._hash_password`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `if _BCRYPT_AVAILABLE:` selects the bcrypt path; the else branch is the SHA-256 fallback documented in the same docstring ('weak fallback is development-only'). Production is already refused at lines 3484-3487, so the fallback cannot serve production.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-000717 — `core/database.py:3485`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `DatabaseManager._hash_password`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `_BCRYPT_AVAILABLE` is a capability flag set by the optional-import guard (lines 45-49: `try: import bcrypt; _BCRYPT_AVAILABLE = True except ImportError: _BCRYPT_AVAILABLE = False` + warning), so truthiness is the correct test; in production the missing flag raises CredentialLifecycleError('BCRYPT_REQUIRED').
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-000726 — `core/database.py:3320`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `DatabaseManager._bootstrap_passwords`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Same capability flag in `_bootstrap_passwords`; docstring 'Resolve the same secure policy used by desktop setup and reset'. `is_production_environment() and not _BCRYPT_AVAILABLE` raises; a legitimate zero cannot occur for an import flag.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-000995 — `core/database.py:4813`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `DatabaseManager.save_imported_multi_tab_data_atomic.count`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `count(key, ok, *, review=False, reason='')` is the atomic import's per-entity counter: `amount = 1 if not isinstance(ok, int) else ok`, `if amount:` accumulates and increments `results['imported']`, `elif review:` records an explicit REVIEW_REQUIRED row (4814-4831). Zero means 'nothing imported for this entity' and is handled.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-001026 — `core/database.py:6531`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `DatabaseManager.save_survey_records`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `audit_report_id = next(iter(contexts))[1] if len(contexts) == 1 else None` exists only to type the audit row (`entity_type='daily_report' if audit_report_id else 'survey_batch'`). The subject is a primary-key report id; None means 'more than one context', the intended branch.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-001116 — `core/database.py:4223`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class A)
- **Symbol:** `DatabaseManager.save_daily_report`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** `save_daily_report` parses report_date with the single format '%Y-%m-%d' and swallows the ValueError. The column is `report_date = Column(Date, nullable=False)` (core/database.py:337), so a non-parseable string cannot be stored silently: SQLAlchemy fails at bind time and the caller's transaction rolls back. Every producer of a string emits ISO: excel_intelligence.py:1624 `.isoformat()`, mineru_engine.py:1600 `.isoformat()`, w1_well_info.py:723 and w2_Daily_Report.py:1869 `yyyy-MM-dd`.
- **Classification:** DOMAIN_DECISION_REQUIRED
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** Should an unparseable report_date be rejected at the persistence boundary with a domain message instead of surfacing as an ORM bind error?

## INV34-001117 — `core/database.py:4901`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class A)
- **Symbol:** `DatabaseManager.save_imported_multi_tab_data_atomic._number_value`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** `_number_value` returns None for absent, non-numeric or non-finite values and its callers test exactly that: `if value not in (None, '') and _number_value(value) is None and ...` (4941) and `elif _number_value(row.get('working_pressure')) is None:` (4962) - None routes the row to validation/review, per the comment 'Validate every row that would otherwise be discarded'.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-001119 — `core/database.py:5070`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class A)
- **Symbol:** `DatabaseManager.save_imported_multi_tab_data_atomic`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** The parsed `hours` only decorates the remarks text (`hrs = f'[HRs: {hours:.0f}] '`, 5068); the persisted row is SevenDaysLookahead, whose columns (core/database.py:1706-1725) contain no hours field. A failed parse drops the prefix and keeps the remarks - no numeric loss.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-001125 — `core/database.py:4901`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class A)
- **Symbol:** `DatabaseManager.save_imported_multi_tab_data_atomic._number_value`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** Same site as INV34-001117 (core/database.py:4901): duplicate record of the same construct; the contract quoted there decides both.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-001126 — `core/database.py:4901`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class A)
- **Symbol:** `DatabaseManager.save_imported_multi_tab_data_atomic._number_value`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** Same site as INV34-001117 (core/database.py:4901): duplicate record.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-001258 — `core/ddr_import_service.py:685`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class A)
- **Symbol:** `DDRImportService._execute_import`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** `session.close()` in a `finally` whose handler is `pass`: a close failure must not mask the import's original exception (`logger.error('Import rollback failed', exc_info=True)` is the rollback path above it). The same contract is implemented in core/database.py `release_session`.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-001321 — `core/ddr_import_service.py:149`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `DDRImportService._resolve_import_well`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `fallback = session.get(Well, self.well_id) if self.well_id else None` is a primary-key presence test; the well is used only to scope the candidate query to the same project before identity resolution by code/name (lines 151-156). A falsy id means 'no well context supplied'. Covered by tests/test_ddr_forensic_regressions.py:368.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-001370 — `core/ddr_pdf_export.py:64`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `numeric-get-default` (HIGH, class A)
- **Symbol:** `DDRPDFExporter.export`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** The construct is `return False` in the export error handler (lines 62-64) - a boolean success signal for `export(...) -> bool`, not a numeric measurement. The rule that raised the finding (numeric-get-default) does not apply to this construct.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-001380 — `core/ddr_pdf_export.py:64`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class A)
- **Symbol:** `DDRPDFExporter.export`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** Same site as INV34-001370 (core/ddr_pdf_export.py:64): the returned value is a boolean, so the or-zero rule mis-fired here.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-002042 — `core/import_quality.py:736`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class A)
- **Symbol:** `ImportValidator.validate_rows`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** The ordering check `float(depth_out) < float(depth_in)` can only raise when a value is non-numeric, and that case is already reported above it: both depth_in and depth_out are in `NUMERIC_FIELDS` (676-677), whose loop (724-731) emits `report.error(sheet, row_number, 'Must be numeric', field, value)`.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-002065 — `core/managers.py:434`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `broad-exception` (HIGH, class A)
- **Symbol:** `DrillingManager.calculate_annular_velocity`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** On failure the facade returns `{'ft_min': 0, 'm_min': 0, 'status': str(exc)}` while the sibling `calculate_hsi` two methods above returns None. The single caller renders `result.get('ft_min', 0)` into the field and ignores `status` (tabs/w3_drilling_report.py:778-781); the widget minimum is documented in that file as the 'not computed' state, so no wrong number reaches the screen - but the dict presents 0 ft/min as a value to any other consumer and the error text never reaches the user.
- **Classification:** DOMAIN_DECISION_REQUIRED
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** Should a failed annular-velocity computation report an absent value (like calculate_hsi/None) instead of zeros, and should the widget surface `status`?

## INV34-002066 — `core/managers.py:425`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `broad-exception` (HIGH, class A)
- **Symbol:** `DrillingManager.calculate_hsi`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** `EngineeringManager.calculate_hsi` returns None on failure and its only caller passes the result through `_set_calc(self.hsi, hsi_val)` (tabs/w3_drilling_report.py:737), whose docstring says 'Show a real result, or fall back to the explicit "not computed" state' and which maps None to the field minimum. The failure stays visible.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-002069 — `core/managers.py:316`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class A)
- **Symbol:** `MenuManager.apply_permissions`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** `apply_permissions` disables only the UI action (`auto_save_action.setEnabled(not is_viewer)`). The mutation path is independently gated: the timer calls `AutoSaveManager.save_widget` -> the widget's own `save_changes`/`save_data` (core/managers.py:79-86), and those tab save paths enforce their own permission contract (tabs/w5 save_all_data fail-closed, tabs/w16 save_data SYSTEM_ERROR, core.permissions.require_permission). A viewer cannot persist through this affordance.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-002072 — `core/managers.py:123`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `broad-exception` (HIGH, class A)
- **Symbol:** `TableManager._widget_for`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** `_widget_for` imports QTableWidgetItem/Qt inside a try and returns None when the optional Qt binding is unavailable; the caller treats None as 'no widget for this value'. Optional dependency guard, not a swallowed domain failure.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-002075 — `core/managers.py:316`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class A)
- **Symbol:** `MenuManager.apply_permissions`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Same site as INV34-002069 (core/managers.py:316): duplicate record.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-002076 — `core/managers.py:316`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class A)
- **Symbol:** `MenuManager.apply_permissions`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Same site as INV34-002069 (core/managers.py:316): duplicate record.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-002095 — `core/managers.py:330`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `ExportCoordinator.get_export_metadata`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `report = self.db.get_daily_report_by_id(report_id) if report_id else {}` is an id presence test feeding the metadata dict; the same idiom is used and validated across the module (e.g. professional_export.py:51-53 raises when the fetched report does not belong to the well).
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-002319 — `core/professional_export.py:179`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `ProfessionalExcelExport.export`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `logs = ... if report_id else []` - a primary-key id presence test in the export section builder; the same parameter is validated at the top of the export (professional_export.py:51-53: `if report_id and (not report or report.get('well_id') != well_id): raise ValueError`).
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-002320 — `core/professional_export.py:202`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `ProfessionalExcelExport.export`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Same idiom as INV34-002319: `... if report_id else ...` id presence test (core/professional_export.py:202).
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-002321 — `core/professional_export.py:213`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `ProfessionalExcelExport.export`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Same idiom as INV34-002319 (core/professional_export.py:213).
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-002322 — `core/professional_export.py:345`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `ProfessionalExcelExport.export`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Same idiom as INV34-002319 (core/professional_export.py:345).
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-002327 — `core/professional_export.py:51`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `ProfessionalExportMetadata.build`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `report = db_manager.get_daily_report_by_id(report_id) if report_id else {}` is guarded by the very next statement - `if report_id and (not report or report.get('well_id') != well_id): raise ValueError('Export report must belong to the selected well')` (52-53) - and the selected well is validated on the next line.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-002333 — `core/profile_import_engine.py:687`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class A)
- **Symbol:** `ProfileImportEngine._build_unmerged_cache`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** The merged-cell scan builds the set of slave cells to skip (line 693: `if (r, c) in merged_slaves: continue`). If it fails, slave cells are no longer skipped - but openpyxl returns None for non-anchor cells of a merged range, so the result is an unread cell, not a duplicated value. A failed optimisation degrades safely.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-002454 — `core/profile_import_engine.py:752`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class A)
- **Symbol:** `ProfileImportEngine._extract_date_triplet`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** `_extract_date_triplet` returns None when the three cells cannot be parsed, and its caller tests it: `if val is not None: ... extracted_data[section][key] = val` (line 193). None is the documented 'not extracted' signal; no wrong date is written.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-006875 — `core/database.py:3485`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class A)
- **Symbol:** `DatabaseManager._hash_password`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Same site as INV34-000717 (core/database.py:3485): duplicate record.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-006876 — `core/database.py:3509`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class A)
- **Symbol:** `DatabaseManager._verify_password`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** `_verify_password` tries bcrypt for non-`sha256:` hashes; if bcrypt raises (malformed or foreign stored hash) execution falls through to the SHA-256 branch (`secrets.compare_digest`, 3512-3519) and then to the legacy static-salt comparison. A failed bcrypt check can therefore never return True - authentication fails closed.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-006877 — `core/database.py:3510`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class A)
- **Symbol:** `DatabaseManager._verify_password`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Same site as INV34-006876 (core/database.py:3510): the `pass` body is that fall-through path.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-006916 — `core/database.py:4224`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class A)
- **Symbol:** `DatabaseManager.save_daily_report`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Same site as INV34-001116 (core/database.py:4224): duplicate record of the report_date boundary question.
- **Classification:** DOMAIN_DECISION_REQUIRED
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** Should an unparseable report_date be rejected at the persistence boundary with a domain message instead of surfacing as an ORM bind error?

## INV34-006954 — `core/database.py:4901`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class A)
- **Symbol:** `DatabaseManager.save_imported_multi_tab_data_atomic._number_value`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** Same site as INV34-001117 (core/database.py:4901): duplicate record.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-006974 — `core/database.py:5070`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class A)
- **Symbol:** `DatabaseManager.save_imported_multi_tab_data_atomic`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Same site as INV34-001119 (core/database.py:5070): duplicate record.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-006975 — `core/database.py:5071`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class A)
- **Symbol:** `DatabaseManager.save_imported_multi_tab_data_atomic`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Same site as INV34-001119 (core/database.py:5071): duplicate record.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-007009 — `core/database.py:5389`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class A)
- **Symbol:** `DatabaseManager.save_imported_multi_tab_data_atomic._fwf`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** `_fwf` returns None for absent or non-numeric fuel/water values, and the derived fields are computed only when all three inputs exist: `if None not in (fuel_stock, fuel_recv, fuel_cons): fw['fuel_remaining'] = ...` (5394-5397), likewise water. An unparseable reading yields 'not computed', never a fabricated total.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-007618 — `core/import_quality.py:737`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class A)
- **Symbol:** `ImportValidator.validate_rows`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Same site as INV34-002042 (core/import_quality.py:737): duplicate record.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-007635 — `core/managers.py:317`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class A)
- **Symbol:** `MenuManager.apply_permissions`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Same site as INV34-002069 (core/managers.py:317): duplicate record.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-007637 — `core/managers.py:455`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class A)
- **Symbol:** `WindowStateManager.save`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** `save()` persists only window geometry and dock state through QSettings (`setValue('window/geometry', ...)`, `setValue('window/state', ...)`, lines 450-455). A failure to remember window layout is a cosmetic UI preference; no domain state is written.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-007638 — `core/managers.py:455`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class A)
- **Symbol:** `WindowStateManager.save`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Same site as INV34-007637 (core/managers.py:455): duplicate record.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-007673 — `core/profile_import_engine.py:688`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class A)
- **Symbol:** `ProfileImportEngine._build_unmerged_cache`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Same site as INV34-002333 (core/profile_import_engine.py:688): duplicate record.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-007678 — `core/profile_import_engine.py:753`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class A)
- **Symbol:** `ProfileImportEngine._extract_date_triplet`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Same site as INV34-002454 (core/profile_import_engine.py:753): duplicate record.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

## INV34-008737 — `core/managers.py:454`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class A)
- **Symbol:** `WindowStateManager.save`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Same site as INV34-007637 (core/managers.py:454): duplicate record.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch
- **Remaining question:** none

