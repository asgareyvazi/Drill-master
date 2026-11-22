# M300–M302 — value lineage for accepted and imported values, read-only lineage UI

UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED. SYNTHETIC golden workbook only. Lineage is read-only: no
code path in `core/import_value_lineage.py` or `dialogs/value_lineage_dialog.py` writes to the database, and no
stored value is ever repaired.

## M300 — check outcomes for review items

| Check | When |
|---|---|
| MATCH | stored value equals the expected value |
| CHANGED_SINCE | stored value differs from the expected value |
| NOT_CHECKED | no reliable expected value (e.g. a conversion is declared and there is no snapshot); always with a reason |
| UNREADABLE | corrupt payload or correction history |
| NOT_APPLICABLE | the item is not ACCEPTED (pending, rejected, ignored) |

Expected value, in this order, never guessed: latest correction → the value persisted at acceptance
(`target_at_creation`) → the accepted normalized value only when no unit conversion is declared → otherwise
NOT_CHECKED. Every result carries `reason`, `expected_basis` and `identity = review:<id>`.

* Golden-fixture fact: its review rows carry no normalized value. An accepted proposal without a value that is still
  empty gives MATCH with the reason "the accepted proposal carried no value and the field is still empty".
* Value MATCH/CHANGED_SINCE is tested with the accepted `depth_0600` proposal (155) produced when R11 is blank.
* M273 change: two assertions on pending items moved from NOT_CHECKED to NOT_APPLICABLE (a test semantics update,
  with comments; no assertion removed).

## M301 — imported values without a review item

* Stable identity `iv:<report>:<table.field>:<fingerprint16>`; **no review item is created**.
* Stages from the last `ddr_import` audit and the Excel `field_provenance` or PDF `mineru_provenance`;
  `later_changes` lists the authored audits after the import.
* Verified: golden `depth_0000` (R9 = 155) → MATCH, no new review item; a later typed "160" → CHANGED_SINCE with
  "155.0 -> 160.0"; R9 = `1,500` → NOT_APPLICABLE pointing at its review item; `wob` → NOT_CHECKED (no
  provenance); a manual report → NOT_CHECKED (no import record).
* Tests: `tests/test_m300_m301_value_lineage.py` and the updated `tests/test_m273_import_value_lineage.py`.

## M302 — read-only lineage UI

* `dialogs/value_lineage_dialog.py`: check and reason, identity, expected value and basis, stored-now, the five
  stages, every correction, later typed changes. No input widgets, no editable cells, no save action.
* Entry points: "🧬 Lineage…" in the Import review dialog (one selected item) and in the W2 value-states dialog
  (selected header field). Both open the dialog window-modal without blocking.
* `tests/test_m302_lineage_ui.py` drives the real path: `DailyReportWidget` → value-states dialog → select a field →
  click the button; and Import review dialog → select the corrected item → click. It asserts the shown values and
  that audit, state, review-item counts and the report row are unchanged.
