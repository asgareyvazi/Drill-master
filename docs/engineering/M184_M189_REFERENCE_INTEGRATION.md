# M184–M189 Tubular reference library in the engineering modules

Status: **UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.** The library ships empty (M181). Every test item
is synthetic.

## 1. Shared service (M189)

All modules use `core/engineering/reference_binding.py` (contract `tubular-binding-v1`). The M157 snapshot
store (`core/engineering/tubular_reference.py`) is unchanged.

### Binding

A **binding** is `{contract, snapshot, fields: {module_key: library_field}, unavailable: [...]}`. It is stored
under the key `tubular_reference` on the component the user filled.

- The snapshot is the immutable M157 snapshot: set id, name, version, set and item fingerprints, and the spec
  with its provenance. It is fingerprinted, and `make_binding` refuses a snapshot that fails `verify_snapshot`.
- Only values present in the library are filled. A value missing from the library is listed in `unavailable`
  and left to the user: it is shown as 0 in the widget, but it is never treated as a library value.
- **No yield strength, burst, collapse, tension or torque rating is ever filled.** Yield is never inferred from
  a grade.

### When a binding holds

`binding_holds` / `attach` keep a binding only while every bound value is unchanged (numbers within 1e-9, text
compared after stripping).

- Editing any bound value drops the binding.
- Clearing a value counts as an edit.
- Keys the module does not hold are not compared. For example, the Hydraulics table has no grade column.

### Drift

`drift(db, snapshot)` compares a stored snapshot with the database. It never re-reads values into a case.

| State | Meaning |
|---|---|
| MATCH | The set version and item fingerprints are unchanged. Newer published versions are reported as "NOT applied". |
| DIFFERENT | The set fingerprint changed, the version is no longer PUBLISHED, or the item is missing from it. |
| NOT_REPRODUCIBLE | That set version is not in this database (for example, a case opened in another database). The snapshot itself stays valid. |
| UNREADABLE | The snapshot fails its own fingerprint, is missing, or the check raised an exception. |

`drift_report` finds every binding inside a case's inputs. `summarize` turns the result into one line, for
example `Library references: 1 MATCH`.

## 2. Module integration

| Module | Entry point | What is filled | What is stored |
|---|---|---|---|
| Drill-string component dialog (Volumes, Hydraulics, Weight / T&D, Kill Sheet table) | `AddPipeDialog` **Library…** button (`apply_library_snapshot`) | OD, ID, weight, grade, connection, tool-joint OD. The type is set from the library component type (DP / HWDP / DC). | The component dict carries the binding, and the `extra:pipes` case input stores it. |
| Hydraulics table | Rows keep the binding in column 0 (`_hy_row_binding`) | — | Editing a bound cell drops the binding. |
| Casing Strength (W13) | **Library…** button (`load_casing_from_library`) | OD, ID and weight from the library. Wall from the library, or DERIVED as (OD − ID)/2 and labelled so. | Origin kind `reference` with the binding. Field provenance `reference` / `derived` / `unknown`. Yield stays `unknown` until the user enters it, and is then recorded as `user`. |
| Well Architecture (W3b) | Casing **Library…** button (`apply_library_to_casing`) | OD, ID (left unknown if unavailable, never derived), weight (unset if unavailable) and grade | The binding is frozen with the architecture revision only while it holds. Unbound revisions keep their component SHA-256. `casing_inputs` and `load_casing_from_architecture` pass the binding to Casing Strength. |
| Case reopen (all W13 contracts) | `CaseBar.reopen` → `reference_report` | — | The status line shows the drift summary of the stored snapshots. Nothing is recalculated from today's library. |

The methods are not changed. The M126 / M127 goldens and the M127 boundaries (soft-string Johancsik T&D, the
TR 5C3 pipe-body subset) are unchanged. Tests confirm that results are identical with and without a library
pick.

## 3. Limitations (recorded, not hidden)

- **Schematic JSON:** the W3b schematic JSON save/load does not carry bindings. A binding is persisted only by
  freezing an architecture revision. A loaded schematic file therefore has no library link, and the values stay
  as user values.
- **Cement:** Cement Volume, Balanced Plug and Buoyancy are scalar worksheets. They have no library button.
  Architecture-derived cement worksheets cite the frozen revision, which carries the binding.
- **Display of unknown weight:** in the W3b table, an unavailable library weight is shown as not recorded.
  `to_schematic` still writes 0.0 for an unknown architecture weight. This is a pre-existing behaviour, and
  `casing_inputs` never uses it to infer anything.
- **No owner-approved tubular data exists** (M181). The feature is qualified with synthetic sets only.

## 4. Evidence

- `tests/test_m184_m189_reference_integration.py`: real Qt widgets and real SQLite files, including a
  close-and-reopen persistence test. It covers:
  - service unit behaviour;
  - all four drift states;
  - the pipe dialog: keep, drop and unavailable values;
  - Volumes, Hydraulics and Weight cases, each with case save → MATCH → reopen;
  - Casing Strength with yield unknown → user;
  - architecture freeze, reload and hand-off to Casing Strength.
- `tests/test_m181_m183_tubular_import.py` and `tests/test_m157_m160_tubular_reference.py`.
