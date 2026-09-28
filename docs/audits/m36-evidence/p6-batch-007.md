# P6 p6-batch-007 — class class E 37 / class D 8 (optional-resource loaders, narrow parser guards, dialog loaders): D:8, E:37

records **45** over **44** sites · INTENTIONAL: 18 · DUPLICATE/FALSE-POSITIVE: 14 · VERIFIED-CORRECT: 13

## New findings (found while adjudicating this batch)

### NEW-P6-002 — `app.py:57` (LOW-MEDIUM, class E (comment/behaviour mismatch, diagnostics))

- **Trigger:** `_setup_logging` cannot create the rotating file handler (read-only profile) and hits `except OSError`
- **Observed:** The handler body is `pass`. The surrounding comment and the module docstring promise the opposite: 'A read-only profile must not prevent the UI from starting. The warning is visible on stderr, without including configuration values.' (58-59) and 'Configure a rotating user-data log with a safe stderr fallback.' (39) - but nothing is written at that moment; only the console handler attached afterwards (62-65, WARNING level) will show later log output.
- **Deciding contract:** The start-up requirement itself is documented and satisfied - the UI must start with a read-only profile - and console logging still works, so no data or computation is affected. What is not implemented is the *stderr warning* the comment claims.
- **Reachable:** yes - any read-only/locked user-data directory (the OSError path this handler exists for).
- **Status:** recorded, not patched
- **Why not patched here:** the fix direction is a product choice: emit the promised warning (one `print(..., file=sys.stderr)` with no configuration values) or correct the comment. Patching either way changes user-visible behaviour or documentation, so it is recorded as the batch's next action rather than decided inside an audit batch.
- **Next action:** decide warn-vs-reword; if 'warn', add the stderr line plus a regression that captures stderr for a read-only log directory, then commit separately.

## INV34-000039 — `app.py:57`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class E)
- **Symbol:** `_setup_logging`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Start-up robustness with a documented reason ('A read-only profile must not prevent the UI from starting', 58) - the app must start even when the rotating log file cannot be created, and logging still reaches stderr through the console handler attached a few lines later (62-65, WARNING level, added to the root logger at 69-71). Residual recorded separately as NEW-P6-002: the comment also claims a warning is printed at that moment, which this branch does not do.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-000077 — `core/ai_import_mapper.py:38`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `get_selected_model`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** Second register record for core/ai_import_mapper.py:38 - the identical reader construct in `configured_model` (settings file instead of catalog; same documented opt-in contract), already adjudicated under INV34-000078: an absent settings file means 'no model configured' ("")
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-000078 — `core/ai_import_mapper.py:31`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `model_catalog`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** Optional AI resource: the module's contract is 'Optional offline-safe local AI assistant ... AI is opt-in and advisory only. Deterministic import validation remains the source of truth; an unavailable Ollama service produces a clear capability status and never blocks non-AI imports.' (1-5). A missing/unreadable model catalog therefore yields an empty catalog, and the capability status - not an exception - is how the caller learns AI is unavailable. No import path depends on it.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-000102 — `core/base_tab.py:398`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class E)
- **Symbol:** `DrillTabBase.get_well_name`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Display fallback chain for a tab header: in-memory name, then one DB look-up, then the neutral label `"No well selected"` (401). A DB failure yields the neutral label rather than a fabricated well name, and nothing is written.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-000161 — `core/canonical_mapper.py:203`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class E)
- **Symbol:** `review_item`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** `mapping_certainty(confidence or 0, mapping_method)` (core/canonical_mapper.py:203): the callee's documented ladder (core/canonical_schema.py:565-587) maps *any* confidence below 0.50 (deterministic) or below 0.85 (fuzzy) to LOW, so 0 - the value used for an absent or unparseable confidence - and an explicit 0 produce the same tier. 'Confidence is never inflated' (570-572): the coalesce cannot raise a tier, and it cannot lower one either (there is no tier below LOW for a known confidence).
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-000175 — `core/canonical_schema.py:576`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `mapping_certainty`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** `except (TypeError, ValueError): return "LOW"` inside `mapping_certainty`: an unparseable confidence takes the lowest certainty tier, i.e. the conservative end of the documented ladder (565-587) under the module's own 'Confidence is never inflated' rule (570-572). Returning nothing or raising would be worse; returning HIGH/MEDIUM would be a fabrication.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-000276 — `core/data_quality.py:33`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `DataQualityService.for_report`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `report = self.db.get_daily_report_by_id(report_id) if report_id else None` - the subject is a DailyReport primary key (positive); the None fallback means 'no report selected' and the metrics list is simply empty for it (no DB call with an invalid id).
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-000280 — `core/data_quality.py:181`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `DataQualityService.for_well`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** The register's line carries the statement start (`total_reports = len(reports)`, 181) whose *guard* sits inside the expression on 183; the guarded quantity is provably non-zero: the method returns early when the query yields no reports (`if not reports: return [QualityMetric("Well completeness", 0, "critical", "No reports")]`, 178-179), so `len(reports) >= 1` and the truthiness test cannot take a division-by-zero path. No fabricated rate is produced for an empty well.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-001134 — `core/database_reset.py:67`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class E)
- **Symbol:** `reset_configured_database`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** `except FileNotFoundError: pass` around `Path(f"{candidate_path}{suffix}").unlink()` - the canonical idempotent-delete guard: the goal is 'the file must not exist afterwards', and it does not, whether it was removed now or was already gone. Any other OSError propagates.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-001402 — `core/document_import.py:178`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class E)
- **Symbol:** `pdf_to_xlsx`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Tier-3 OCR *metrics* collection around an optional external engine (pytesseract): the block appends diagnostic metrics (page, engine, confident word count, mean confidence), and its failure only means those metrics are not reported. The actual tier-3 result is produced from `tier3_rows` afterwards (181-184) - the swallow cannot change extracted data.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-001427 — `core/domain_records.py:56`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class E)
- **Symbol:** `is_metadata_value`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** A *probe*, not a decision: `ast.literal_eval(value)` tries to recognise an embedded literal and the swallow falls through to the explicit type/filename checks that follow (`return isinstance(value, (dict, list, tuple, set)) or (...)` , 58-59). The fallback path is the method's normal 'not a literal' answer, so the exception is an expected probe outcome rather than a hidden failure.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-001786 — `core/excel_intelligence.py:1236`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class E)
- **Symbol:** `ExcelIntelligence.__init__`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Optional workbook metadata: `workbook.filename = str(source_file)` is an attribution field on the in-memory workbook object (openpyxl) and a failure only leaves it unset - it is not part of any extraction or persistence contract.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-001895 — `core/excel_intelligence.py:914`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `FieldExtractor._normalize_numeric_value`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** `except (ValueError, TypeError): return value` (914-915): this helper's contract is 'the numeric value when it parses, otherwise the original text', which is what the caller needs in order to keep non-numeric content (dates, names) intact while normalising numbers. Returning the input unchanged cannot invent a measurement.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-001896 — `core/excel_intelligence.py:833`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `FieldExtractor._validate_engineering`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** `except (ValueError, TypeError): return "invalid_type"` (833-834): the failure is reported as a *named classification* rather than a silent value - the caller receives `"invalid_type"` and can act on it. Nothing numeric is fabricated for an unparseable cell.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-001906 — `core/functions.py:75`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class E)
- **Symbol:** `CentralFunctions.validate_drilling_data`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** The guard cannot hide an unflagged problem: the loop just above already validates every numeric field, including `depth_in`/`depth_out` (`float(value)` with `errors[field] = "... must be a number"`, 59-67), so by the time this comparison runs a parse failure has a user-visible error attached to the field. The swallow exists only so the comparison itself does not raise a second, duplicate error for the same input.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-002108 — `core/mapping_store.py:19`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `MappingStore._load`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** Optional persisted mapping file: an unreadable/corrupt store yields the documented empty store `{"mappings": {}}` (19-20) - the same value a first run produces - so the caller sees 'nothing remembered yet' instead of an exception. Nothing is written back by this read path.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-002199 — `core/mineru_engine.py:646`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `MinerUAdapter.parse_file`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** `except MinerUOutputError as exc: return self._failure(...)` (646-647): same shape as INV34-002201 - a typed error is converted into the module's failure result (with method and reason) rather than a silent fallback.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-002201 — `core/mineru_engine.py:602`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `MinerUAdapter.parse_file`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** `except subprocess.TimeoutExpired as exc: return self._failure(source_display, ...)` (602-604): the failure is *returned as an explicit failure result* carrying the reason - not swallowed. MinerU is the documented external-optional engine, so a timeout becomes a reported capability/parse failure and the non-MinerU paths stay available.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-002203 — `core/mineru_engine.py:1048`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `_parse_html_table`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** `_parse_html_table` returns `([], [])` both on a parser error and when the document contains no table at all (`if not parser.rows: return [], []`, 1050-1051) - i.e. the failure mode is the function's documented 'no table found' answer, and the caller treats it as 'nothing to import' rather than as data. TypeError/ValueError cover the stdlib parser's documented non-string/malformed-input errors.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-002258 — `core/performance.py:113`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class E)
- **Symbol:** `ProgressTracker.advance`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** A progress callback must not be able to abort the operation it reports on: `cb(pct, self.current, self.total)` is a UI hook, and letting its exception propagate would turn a cosmetic failure into a failed operation. No stored or computed value depends on the callback.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-002269 — `core/performance.py:22`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `get_file_size_mb`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** A size *metric* for progress display: an unreadable file reports 0.0 MB. The value is used for the progress/indicator text, not for any decision about the file's contents, and the subsequent processing of that file reports its own errors. Residual (recorded, not a defect claim): 'unknown size' is displayed as 0.0 MB rather than as 'unknown'.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-002767 — `core/runtime_config.py:102`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `read_mineru_settings`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** Optional MinerU settings file: an unreadable or non-dict payload yields `{}` (102-103), the same 'no settings' value the module uses when the file is absent (`value if isinstance(value, dict) else {}`, 101). MinerU is the documented external-optional engine; callers fall back to their defaults.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-002794 — `core/selection_manager.py:307`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `SelectionManager.select_full_context`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Second register record for core/selection_manager.py:307 - the same optional-id truthiness test two lines below (report id), already adjudicated under INV34-002795: same documented optional-id contract
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-002795 — `core/selection_manager.py:305`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class E)
- **Symbol:** `SelectionManager.select_full_context`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `select_all`'s documented contract makes each id optional: 'Select well + wellbore + section + report in one call. Useful after import to set everything at once. Emits signals in correct order: well -> wellbore -> section -> report' (294-300). The subjects are primary keys (positive), so the truthiness test is exactly the 'this id is not part of the selection' test - a not-provided id must not be selected.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-002813 — `core/standards.py:42`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `bop_test_interval_days`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** A configuration value with a documented fallback: `max(1, int(cfg["bop_test_interval_days"]))` inside a try whose `except (TypeError, ValueError): return default` (42-43) returns the caller's default when the configured value is unusable, and the `max(1, ...)` already guards the lower bound for a parseable value. No hard-coded number is invented: `default` comes from the call site.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-002818 — `core/survey_records.py:64`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `plot_series.finite`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** Fail-closed *exclusion*: the predicate asks whether every coordinate of a record is a finite number, and an unparseable value raises out of `float(...)`/`math.isfinite` into `return False` (64-65) - the record is then filtered out of `usable` (66). The swallow makes the record unusable, not usable; a survey with unreadable numbers can never reach the trajectory maths through this path.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-002851 — `core/text_utils.py:27`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `safe_float`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** `safe_float(value, default=0.0)` is *defined* to return the caller's `default` when the value is absent or unparseable (`float(value) if value is not None else default` plus `except (ValueError, TypeError): return default`, 24-28). The default is an explicit parameter at every call site, so the helper cannot invent a number the caller did not choose.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-002852 — `core/text_utils.py:34`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class E)
- **Symbol:** `safe_int`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** Second register record for core/text_utils.py:34 - the identical construct in `safe_int` (int-of-float with the caller's default), already adjudicated under INV34-002851: same documented default-parameter contract (31-35)
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-002895 — `core/universal_import.py:109`

- **Rule / kind:** `R-EXC-PASS` / `broad-exception` (HIGH, class E)
- **Symbol:** `WorkbookScanner.scan`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Optional metadata on an import result: `result["file_size"] = Path(file_path).stat().st_size` inside an `except Exception: pass` (107-110) means the key is simply absent when the size cannot be read. The import itself continues and reports its own status; no extracted value depends on the file size.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005735 — `tabs/w3c_section_data.py:840`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class D)
- **Symbol:** `_ServiceCompanyDialog.__init__`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** `if company_id: self._load()` - a Company primary key tested for truthiness before the dialog loads its data; with no company selected the dialog stays empty instead of querying with an invalid id.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005743 — `tabs/w3c_section_data.py:370`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class D)
- **Symbol:** `CasingReportTab.load_from_dict.sv`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** Second register record for tabs/w3c_section_data.py:369/370 - the identical `sv` helper of the second dialog class in the same file, already adjudicated under INV34-005747: same caller-supplied-default loader contract
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005745 — `tabs/w3c_section_data.py:212`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class D)
- **Symbol:** `CementReportTab.load_from_dict`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Legacy thickening-time text is parsed into two spin boxes; on an unparseable/partial value the boxes keep their current (default) contents - no time is invented, and the operator sees the field as it was rather than a fabricated schedule entry.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005746 — `tabs/w3c_section_data.py:224`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class D)
- **Symbol:** `CementReportTab.load_from_dict`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** The handler's own comment is the contract: 'malformed legacy materials JSON - leave table empty' (225). The table was reset before parsing, no rows are invented from a corrupt blob, and the typed guard names the expected failure modes (JSONDecodeError/TypeError/ValueError/KeyError).
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005747 — `tabs/w3c_section_data.py:202`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `typed-exception` (HIGH, class D)
- **Symbol:** `CementReportTab.load_from_dict.sv`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** The dialog loaders' `sv(key, d)` helper returns the field's documented default `d` when the stored value is absent or unparseable (`float(v) if v is not None else d` plus `except (TypeError, ValueError): return d`, 200-203) - the same loader pattern already adjudicated in p6-batch-005 for w3 (`safe_val` vs `safe_opt`): the spin box is an operator entry field whose domain includes a legal zero, and the default comes from the call site (`sv("compressive_strength",2500)`, ...).
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-005748 — `tabs/w3c_section_data.py:1221`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class D)
- **Symbol:** `FailureReportTab._load_data`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** `QDate.fromString(...)`/`setDate(...)` do not raise for a bad date string (they yield an invalid/blank date), so this guard is defensive; its consequence if it ever fires is that the date field keeps its previous state - it can never fabricate a date for a report.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-006770 — `app.py:60`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `_setup_logging`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for app.py:57/60 - the `pass` line of INV34-000039's handler, already adjudicated under INV34-000039: start-up robustness; logged as NEW-P6-002 in this batch
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-006804 — `core/base_tab.py:399`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `DrillTabBase.get_well_name`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for core/base_tab.py:398/399 - the `pass` line of INV34-000102's handler, already adjudicated under INV34-000102: the neutral fallback is returned
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-007396 — `core/document_import.py:179`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `pdf_to_xlsx`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for core/document_import.py:178/179 - the `pass` line of INV34-001402's handler, already adjudicated under INV34-001402: OCR diagnostics only; the tier-3 result comes from `tier3_rows` (181-184)
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-007397 — `core/domain_records.py:57`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `is_metadata_value`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for core/domain_records.py:56/57 - the `pass` line of INV34-001427's probe, already adjudicated under INV34-001427: the fall-through answers 'not a literal'
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-007551 — `core/excel_intelligence.py:1237`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `ExcelIntelligence.__init__`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for core/excel_intelligence.py:1236/1237 - the `pass` line of INV34-001786's handler, already adjudicated under INV34-001786: optional workbook attribution metadata
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-007569 — `core/functions.py:76`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `CentralFunctions.validate_drilling_data`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for core/functions.py:75/76 - the `pass` line of INV34-001906's guard, already adjudicated under INV34-001906: the numeric-field loop above already reported 'must be a number'
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-007660 — `core/performance.py:114`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `ProgressTracker.advance`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for core/performance.py:113/114 - the `pass` line of INV34-002258's handler, already adjudicated under INV34-002258: a UI progress hook must not abort the operation
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-007853 — `core/universal_import.py:110`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class E)
- **Symbol:** `WorkbookScanner.scan`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for core/universal_import.py:109/110 - the `pass` line of INV34-002895's handler, already adjudicated under INV34-002895: optional file-size metadata key
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008331 — `tabs/w3c_section_data.py:213`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class D)
- **Symbol:** `CementReportTab.load_from_dict`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for tabs/w3c_section_data.py:212/213 - the `pass` line of INV34-005745's handler, already adjudicated under INV34-005745: the spin boxes keep their defaults
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

## INV34-008347 — `tabs/w3c_section_data.py:1221`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class D)
- **Symbol:** `FailureReportTab._load_data`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** Second register record for tabs/w3c_section_data.py:1221 - the second rule on the same defensive date handler, already adjudicated under INV34-005748: an unparseable date leaves the field's previous state
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only, committed with this batch evidence
- **Remaining question:** none

