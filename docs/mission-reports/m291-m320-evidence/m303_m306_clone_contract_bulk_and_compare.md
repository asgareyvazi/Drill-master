# M303–M306 — clone contract, clone provenance, bulk archive / restore, clone vs source

UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED. SYNTHETIC records only. No formula, constant or rounding
changed; nothing is recalculated by any of these features.

## M303 — adapter matrix (`core/calculation_clone_contract.py`)

`calculation_history._adapters()` has 11 adapters. `ADAPTER_MATRIX` has exactly one contract per adapter table
(test `test_every_adapter_has_exactly_one_clone_contract`; a new adapter without a contract is refused, never
cloned by default).

| Table | Clone | Route | Extra requirement |
|---|---|---|---|
| torque_drag / casing / cement / mse / mud_volume / well_control_kill_sheet calculations | ALLOWED | `save_case` + `clone_of` | scope label of the source kept in the note |
| trajectory_calculations | ALLOWED | `save_case` + `clone_of` | legacy rows keep "unversioned (legacy)" |
| calculation_cases | ALLOWED | `clone_case` (parent_id + `clone_of`) | — |
| directional_plan_revisions | ALLOWED | `save_case` + `clone_of` | the clone is a case, not a plan revision |
| survey_revisions | ALLOWED | `save_case` + `clone_of` | `stations` present and integrity VERIFIED |
| well_architecture_revisions | ALLOWED | `save_case` + `clone_of` | `components` present and integrity VERIFIED |

`clone_check` refuses, with a reason and before any write: no contract; empty or unreadable (legacy raw JSON)
inputs; empty or unreadable stored results ("re-run it instead"); missing required input; integrity not VERIFIED;
source row gone. `calculation_workbench.clone` calls it. The workbench disables Clone and shows the reason in the
tooltip. The M286 message "no readable inputs" is unchanged.

## M304 — clone provenance and D87 identity review

* `clone_provenance(db, case_id)`: source key, copied method and version (`method_kept`), verification status
  CLONE, `recalculated=False`, `approved=False`, label "CLONE — inputs and stored results copied; NOT
  recalculated; NOT approved". The clone note now also says "not approved" and names the source scope.
* Identity of the source, without a schema change: the `calculation_source_links` row has no
  `source_created_at`, so the source's `created_at` is compared with the link's `created_at`.
  VERIFIED (source predates link), SOURCE_REPLACED (source created after the link: a reused id; never compared),
  SOURCE_MISSING, IDENTITY_WEAK (no creation time).
* D87 review: 7 of the 11 history tables have a nullable `created_at` (the six engine snapshot tables and
  `trajectory_calculations`). With a NULL `created_at`, an archive mark could not tell the row from a later row
  that reuses its id. **Change:** archiving such a row is now refused with a reason (restore stays possible for
  legacy marks). Existing marks are not rewritten.

## M305 — bulk archive / restore (`calculation_workbench.bulk_preview` / `bulk_apply`)

* Preview writes nothing: per row WILL / SKIP (already in that state, or listed twice) / REFUSE (gone, no creation
  time, not authorized).
* Apply: one mandatory reason; contract **PER_ROW**: each row is its own transaction (mark + mandatory audit).
  A row whose audit or storage fails is FAILED and leaves no mark; the other rows keep their result.
  `partial=True` whenever some rows are DONE and others REFUSED/FAILED; the message starts with "PARTIAL:" and
  names the counts, with "NOT SAVED (storage error)" for failures.
* Authorization: checked against the real `authorize_change` for `calculation_archive_marks` insert before
  anything is written; an unauthorized bulk is refused as a whole.
* Workbench: "Archive selected…" / "Restore selected…" → preview and reason (`confirm_bulk`) → per-row status
  line.

## M306 — clone vs source (`side_by_side`, `dialogs/clone_comparison_dialog.py`)

Read-only dialog from the workbench ("Clone vs source…"): provenance line, method / version / created / scope of
both, every input and result field with SAME / DIFFERENT / ONLY IN CLONE / ONLY IN SOURCE. `rerun=False` and the
statement "A clone is a copy … not a rerun". A SOURCE_REPLACED or missing source is not compared.

## Tests

`tests/test_m303_m306_clone_contract_and_bulk.py` (7 parametrized refusals + 10 other tests = 17) with M286, M286
authorization and M67: 33 passed, 0 failed / errors / skipped (local, `/tmp/m306.xml`).
