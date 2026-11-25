# M464–M468 — EOWR source-data sections (U1 closed for SYNTHETIC scope)

## M464: audit (before)

`core/report_sections.py` `eowr_manifest()` (manifest v2) marked six record sets as **NOT_RENDERED**:

| Data key | Table | Collected by |
|---|---|---|
| `bit_reports` | `bit_reports` | `EOWRReportEngine._collect_data` |
| `bha_reports` | `bha_reports` | `EOWRReportEngine._collect_data` |
| `time_logs_24h` | `time_logs_24h` | `EOWRReportEngine._collect_data` |
| `time_logs_morning` | `time_logs_morning` | `EOWRReportEngine._collect_data` |
| `requests` | `material_requests` | `EOWRReportEngine._collect_data` |
| `equipment_logs` | `equipment_logs` | `EOWRReportEngine._collect_data` |

All six were queried for the well, but the HTML/PDF body did not render them, and neither did the Excel/CSV sheets. A
failure in any of these queries failed the whole report (`_collect_data` returned `{}`). The time-log queries had no
order. There was no period scope.

## M465–M466: implementation (after)

### Renderer: `core/eowr_sections.py`

`core/eowr_sections.py` (`M464 EOWR source-data sections v1`) is a pure renderer. HTML, PDF, Excel, CSV and the manifest
all use the same analysis.

The sections, in report order:
- `12. Bit records`
- `13. BHA components`
- `14. 24-hour time logs`
- `15. Morning tour time logs`
- `16. Material requests`
- `17. Equipment logs`

Rendering rules:
- **Source.** Each row names its source: table, primary key, and the daily report (`DDR id N #number date`, or
  `no daily report`).
- **Order.** Rows are ordered by their own date, then time of day, then primary key. Undated rows sort last.
- **Values.** Values are reproduced as stored, with the units of the column they were entered in (the W3c bit table
  and the W4 BHA table). Nothing is summed, deduplicated or converted.
  - A missing value is `—`, never `0`.
  - A stored `0` is kept.
- **Unknown keys.** A payload key that is not a known column goes to `Other fields` and is not dropped.
- **Escaping.** All stored text is HTML-escaped. Payloads are user or import data.
- **Bit snapshots.** Each stored bit report is a snapshot. A bit that appears in several snapshots is listed once per
  snapshot, with no identity rule assumed. This is stated in the section note.
- **Legacy BHA.** Legacy named BHA configurations (`{name: [rows]}`) are rendered under their configuration name.

### Section states

| State | Meaning |
|---|---|
| `INCLUDED` | n row(s) from m stored record(s) |
| `NOT_RECORDED` | No row in scope. Stored records with an empty payload are named by ID. Always marked "not a reported zero" |
| `QUERY_FAILED` | The table could not be read. The section says it is not assessed and is not a statement that nothing was recorded |
| `NOT_RENDERED` | A stored payload is not readable as records (for example malformed JSON). The unreadable source IDs and reasons are listed. Rows from readable records are still rendered |

### Engine: `core/report_engine.py` `EOWRReportEngine`

- Each of the six queries runs inside its own SAVEPOINT (`session.begin_nested()`). A failed table becomes `None`
  with status `query-failed` and is logged. The report still renders, and rows already loaded are not expired.
- `generate(well_id, path, fmt, period=None)` takes an optional inclusive `(from, to)` period (dates or ISO strings).
  An inverted or malformed period fails the export (`False`). It never falls back to the whole well.
- **Period filter.** The filter keeps only records dated inside the period.

  | Record set | Dated by |
  |---|---|
  | daily reports, drilling parameters, mud, bit, cement, casing, safety | `report_date` |
  | material requests | `request_date` |
  | equipment logs | `service_date` |
  | cost lines | `cost_date` |
  | time logs and BHA | their daily report |

  Undated records are excluded and counted. The counts appear in the section detail and in the manifest `Scope` entry.
  Sections, surveys, personnel, services and transport are undated and stay whole-well. The cover and the Excel summary
  say so.
- Excel has six new sheets (`BitRecords`, `BHAComponents`, `TimeLog24H`, `TimeLogMorning`, `MaterialRequests`,
  `EquipmentLogs`). A section without rows writes one explicit `Status | Detail` row. CSV is derived from these
  sheets.

### Manifest and provenance

- `core/report_sections.py`: `MANIFEST_VERSION` is now `M320-D report section manifest v3`.
  - The six sections take their status from `eowr_sections.analyse`.
  - A new first entry, `Scope`, states the whole-well or period scope and the undated exclusions.
- `core/report_provenance.py`: a period-scoped EOWR states `scope.period` as the requested period, with the number of
  daily reports inside it.

### UI: `tabs/w11_Export.py`

The End-of-Well tab has a new "Limit to period (dated records only)" option with From/To dates.
- Unchecked, the export covers the whole well. This is the historical behaviour.
- An inverted period is refused with a warning before the file dialog opens.

## Tests

| File | Tests | What is checked |
|---|---|---|
| `tests/test_m464_eowr_source_sections.py` | 15 (corrected in M494 from 16; `pytest --collect-only`) | All six sections with sources, well isolation, chronology, units, `—` for missing values, escaping, unknown keys, legacy BHA, empty → NOT_RECORDED, malformed → NOT_RENDERED, dropped table → QUERY_FAILED, period with undated exclusion, invalid periods, Excel/CSV/PDF, column mapping, benchmark at small scale |
| `tests/test_m467_eowr_mainwindow_journey.py` | 3 | Real `MainWindow` → W11 End-of-Well tab: whole-well export, well switch, period export, inverted period refused |
| `tests/test_m320d_report_sections.py` | updated | The old assertion `Bit reports == NOT_RENDERED` described the defect. It is replaced by a stronger one: the empty payload is NOT_RECORDED, named by ID, and **no** EOWR section is NOT_RENDERED |

The test environment is Linux offscreen Qt. This is not Windows acceptance.

## M468: mutation and benchmark

`tools/quality/mutation_m461_m520.py` has 21 mutants. The first run killed 20. One survived:
`ES-empty-payload-as-included`. A test was added for it, and on re-run it was KILLED. The final result is
**21/21 killed**, with 0 declared equivalent and 0 invalid.

The historical mutant `RS-not-rendered-hidden` (in `tools/quality/mutation_m321_m360.py`) has its anchor moved to
`core/eowr_sections.py` (precedent: the M367 anchor update). It is KILLED.

`tools/quality/benchmark_m468_eowr.py` builds a SYNTHETIC well:
- 60 days;
- 24 logs per day;
- 3 bits per snapshot;
- 12 BHA components;
- a twin well with the same shape.

The expected row counts are computed from the generator parameters, not by the engine:

| Section | Expected | Rendered |
|---|---|---|
| 12. Bit records | 180 | 180 |
| 13. BHA components | 720 | 720 |
| 14. 24-hour time logs | 1440 | 1440 |
| 15. Morning tour time logs | 360 | 360 |
| 16. Material requests | 60 | 60 |
| 17. Equipment logs | 60 | 60 |

All six checks pass:
- HTML generated;
- Excel generated;
- counts equal;
- chronological order, with logs inserted in reverse;
- no twin-well rows;
- Excel row count.

Measured on this sandbox: HTML 0.26 s, Excel 1.37 s, HTML size 700 980 bytes. These are measured values and are not
byte-compared.

## Limits

- Values are shown as stored. No unit conversion is applied, and no plausibility check is applied to bit, BHA or
  request values.
- Bit snapshots are not deduplicated, because no bit identity rule is defined.
- The professional workbook export is unchanged.
