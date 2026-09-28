# DDR import mapping contract

This contract is shared by the Excel and PDF import paths and by the Daily
Report ComboBoxes.  Extraction preserves the original token and source
location in the Import IR; mapping does not replace that provenance.

## Activity Code and Sub-Code

For the OEOC/DDR activity catalogue, numeric values use **one-based DDR
ordinals**:

- `Code=2` means the second authoritative main activity and resolves to the
  application identity `2 - Drilling`.
- `Sub-Code=1` is resolved within the resolved main activity.  With `Code=2`,
  it resolves to `2.1 - Vertical Drilling`.
- A composite token such as `2.1 - Vertical Drilling` is a canonical identity;
  a numeric application code and an exact/normalized label are also accepted.
- Known aliases (for example `DRL`) resolve through the same catalogue.

The persisted value is the stable application identity (`code - label`), not a
Qt index, visible-label coincidence, or raw DDR ordinal.  `itemData` in UI
ComboBoxes carries this identity as well.

A numeric token is treated as an ordinal only for fields proven to use the DDR
activity convention.  Numeric values for unrelated ComboBoxes are not
converted to indices.

## Review behavior

Blank, invalid, out-of-range, ambiguous, and missing-parent Sub-Code values
remain `REVIEW_REQUIRED`.  The importer never selects item zero or any other
default item.  The source value, resolution method, candidates, and reason
are retained in `_combo_resolution` and the common review/persistence
boundary.  Accepted values continue through:

`RawDocument -> Import IR -> canonical mapping -> normalization -> validation -> ReviewItem -> atomic persistence`.

Unresolved activity rows are not silently persisted as a different activity.
Valid rows in the same import may persist atomically; the unresolved source
row remains in review.

## Other ComboBox-backed fields

The same rule applies to mud type, chemical type/unit, status, phase, and any
future catalog-backed field: use stable `itemData`/domain identity, match
code/label/normalized label/alias deterministically, and leave no match
unresolved.  UI reloads use the same identity matcher and explicitly clear an
unmatched ComboBox rather than falling back to its first entry.

## PDF sections

When MinerU is unavailable, the native PDF fallback uses PyMuPDF
`find_tables()` and emits separate semantic sections for the report metadata,
summary/forecast, 24-hour log, morning log, and casing table.  These sections
are adapted to the same `MinerUDocument` and `DocumentNormalizer` route; no
intermediate workbook is created and Excel extraction never invokes MinerU.
