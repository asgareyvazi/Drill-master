# M295–M297 — authored value entry, Excel import value states, supported PDF paths

SYNTHETIC data only (golden workbook fixture, synthetic PDFs). No file under `08-DDR` and no confidential PDF was
opened, parsed, hashed or copied. Real DDR acceptance: **NOT RUN**.
UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.

## M295 — `parse_authored` on the live UI path (commit `ae016a7`)

* Decision: wired, not reclassified. The W2 value-states dialog (`dialogs/ddr_value_states_dialog.py`) has a typed
  column; a typed entry goes through `core.ddr_value_states.parse_authored` and `record_authored`, which writes
  the value, the state event and the mandatory audit in one transaction.
* D86 behaviour verified through the dialog and in the database (`tests/test_m295_authored_value_entry.py`):
  `"312.5"` → REPORTED, `" 0 "` → ZERO, `"N/A"` → NOT_APPLICABLE, `"?"` → UNKNOWN, `"NR"` → NOT_REPORTED;
  `"1,5"`, `"1,500"`, `nan`, `inf`, `"12 m"`, `"abc"` are refused with a message and nothing is stored; an Approved
  report refuses; an audit failure rolls back both the value and the state.
* The W2 header spin boxes are unchanged; they cannot carry a comma.

## M296 — value states in the Excel import (same transaction)

New module `core/ddr_import_value_states.py`, contract `ddr-import-value-states-v1`. Classification uses the
import provenance (original cell text), not the already normalized value, because the normalizer has already run.

| Outcome | Example source text | What happens |
|---|---|---|
| NUMBER | `310`, `0` | value stored by the import as before; ZERO is a state for `0` |
| BLANK | empty cell | stays None; no state is invented |
| TOKEN | `N/A`, `NR`, `?` | import value state + audit, inside the import transaction |
| AMBIGUOUS | `1,500`, `12 ft?`, unit mismatch | **not stored**; a DEFERRED_UNRESOLVED `value_state` review item is created |

* Operator states are never overwritten; an identical re-import writes nothing; a failure in the import rolls back
  the states and their audits (counts stay 0/0/0).
* Not auto-repaired (documented, unchanged): `ValueNormalizer._number` turns `"1,500"` into 1500.0 on its own.
  M296 keeps the value out of the report and sends it to review instead of trusting that conversion.
* Extractor behaviour (documented, unchanged): when R11 (depth 06:00) is blank, the extractor proposes the R9 value
  for `depth_0600` as a REVIEW row; it is stripped unless an operator accepts it.
* Tests: `tests/test_m296_import_value_states.py` (31): zero, empty, unknown, N/A, ambiguous, unit, deferred,
  accepted, re-import, rollback, audit atomicity, dialog display of the pending review.

## M297 — supported PDF paths

* Covered: MinerU output and `parse_pdf_native_fallback` → `mineru_extracted` → `DocumentNormalizer` →
  `import_records`. `_provenance_map` reads the PDF `mineru_provenance` list.
* A blank mapped PDF cell becomes BLANK_EXTRACTION and goes to review; it is **never** automatically NOT_REPORTED.
* OCR-derived or conflicting values are AMBIGUOUS (review). OCR itself stays gated by P4/P5; nothing was enabled.
* Tests: `tests/test_m297_pdf_value_states.py` (6).
