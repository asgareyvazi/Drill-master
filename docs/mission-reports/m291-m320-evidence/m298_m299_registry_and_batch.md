# M298–M299 — value-state registry and batch transaction contract

UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED. SYNTHETIC data only.

## M298 — schema-driven registry

`core.ddr_value_states.ValueField`, `registry()`, `describe()`. One entry per field with: key, label, unit,
allowed states, missing-value contract, validation (engineering bounds from `core.canonical_schema`), provenance
source, and import / UI / persistence support flags. Backward compatible: the registry lists exactly the 11 M272
fields in the same order, and every old call site keeps working. The W2 dialog uses `describe()` as its row
tooltip.

## M299 — batch contract: PER_FIELD (deliberately unchanged from M272)

* `save_batch(db, report_id, entries)` → `BatchResult(saved, refused, failed, partial)`.
* Each field's value, state event and audit share one transaction. One field's failure never leaves a partial row
  for that field; the other fields stay saved (the tested M272 partial-success behaviour is kept).
* `message()`: `Saved N state(s) of M change(s).`, followed by `PARTIAL SAVE`, `Refused: …` and
  `NOT SAVED (storage error …)` parts when they apply. The M272 assertion on "Saved 2 state(s)" is unchanged.
* Fault-injection tests (`tests/test_m298_m299_registry_and_batch.py`, 8 tests): clean batch; refusals; an audit
  fault on one field leaves no value or state row for it; a storage fault is reported as NOT SAVED; the dialog
  reports a partial save.
* `save_batch` keeps one broad `except` marked `# silent-ok:`. The error is not swallowed: it is reported in
  `failed` and in the message. The silent-exception ceiling is unchanged.
