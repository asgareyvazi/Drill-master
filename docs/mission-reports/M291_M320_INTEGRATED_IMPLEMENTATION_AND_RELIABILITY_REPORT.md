# M291–M320 – value states, clone contract, D63 root cause, and the six must-implement engineering items

**UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.** Data scope: SYNTHETIC / SCREENING. Real DDR acceptance,
Windows desktop acceptance and field acceptance were **NOT RUN**.

## Overall status: PARTIAL

The six must-implement items (M274, M277, M280, M281, M287, M288) are implemented end to end: core module,
desktop UI, real tests and an evidence file each. **None** of them is labelled QUALIFIED, because M291–M320 has no
mutation catalogue.

The D63 crash now has an identified root cause and an upstream fix. Applying it means raising the PySide6 pin,
which is an **OWNER DECISION**: the lock stays at 6.8.1.1, so closed windows are still retained on the shipped
pin.

| Commit | Content | CI |
|---|---|---|
| `ae016a7` | M291–M295 | 3.11 ✅, Windows ✅; 3.12/3.13 cancelled at 47 min by the concurrency group (superseded, not failed) |
| `d57f5b2` | M296–M306 | Windows ✅; Source gate ❌ on all three legs. **1 failure:** `test_model_registry::test_only_core_database_creates_a_declarative_base` (`core/ddr_value_states.py:319`, a function named `registry`) |
| `2273aa4` | M307–M320 code, evidence and the `registry` fix | Source ✅ on all 3 legs (72.88 %); Windows ❌ (M320 E layout, fixed in the next commit) |
| final commit | Windows layout fix for M320 E; final report, roadmap, matrix, inventory, M310 profile | see the delivery message |

## A. Delivery verification

* Branch `arena/72010272-drill-master`, pushed fast-forward. `git ls-remote` matches the local HEAD after every
  push.
* Local full suite on the `2273aa4` tree: **5,867 tests, 0 failed, 0 errors, 4 skipped** (3,319 s; Python 3.11.2,
  PySide6 6.8.1.1, offscreen).
* Gates on `2273aa4`, all green:
  * privacy check: 1,773 files, 0 findings;
  * ruff on `core dialogs tabs tests`;
  * exception ceiling (83/83, not raised);
  * dependency audit (FAIL 0), engine inventory, constant inventory, journey index, density-constant inventory;
  * guard tests (`test_model_registry`, release-boundary imports).
* CI on `2273aa4`:
  * **Source release gate** run `45001056902`: ✅ on 3.11 (40 min), 3.12 (53 min) and 3.13 (40 min). The 3.12
    leg measured product coverage (branch + line) at **72.88 % (81,029 / 111,176) over 302 tracked files**,
    against a floor of 45.50 %.
  * **Windows release validation** run `45001056829`: ❌, 1 failure. `test_m49_knowledge_ui::
    test_persian_answer_is_right_to_left_and_long_passages_are_elided` reported a panel `minimumSizeHint` width of
    1,590 ≥ 1,300 px. Cause: the two M320 E buttons sat on the evidence header row. Offscreen Linux fonts are
    narrower, so the local suite did not catch it. With fonts enlarged to Windows-like metrics the regression was
    reproduced (1,275 → 1,487 px).
  * Fix in the final commit: the buttons moved to their own row with the status label, which brings the width
    back to 1,275 px, identical to the pre-M320 E layout. The M320 E UI test now asserts that the citation row is
    no wider than the header row. M49 UI, M122 and M320 E tests: 50 tests, 0 failures.
  * The final commit needs its own CI result; it is recorded in the delivery message, not assumed here.

## Phase register

| Mission | Item | Result | Evidence (`m291-m320-evidence/`) | Class |
|---|---|---|---|---|
| M291 | baseline after the 8th sandbox reset | non-destructive recovery; tree hash identical to the remote | `m291_baseline.md` | DONE |
| M292 | independent audit of M261–M290, residual register | 2 new gaps found (M272-G1, M273-G1), both fixed | `m292_residual_register.md` | DONE |
| M293 | coverage addendum for the M261–M290 source | 72.40 % (78,781 / 108,811) on `b6a6a33` | M261–M290 report addendum | DONE |
| M294 | CI runtime study | D88 timing documented | `m294_ci_runtime_study.md` | DONE |
| M295–M297 | value-state entry (W2 typed column), import value states | comma refusal live (D86) | `m295_m297_*.md` | RESOLVED (synthetic) |
| M298–M299 | field registry and batch contract | `field_registry()` (renamed after the guard failure) | `m298_m299_*.md` | RESOLVED (synthetic) |
| M300–M302 | value lineage + UI | non-blocking lineage dialog | `m300_m302_*.md` | RESOLVED (synthetic) |
| M303–M306 | clone contract (11 adapters), provenance, bulk archive/restore, clone vs source | D87 partially resolved | `m303_m306_*.md` | RESOLVED; D87 PARTIAL |
| M307 | D63 native root cause | freed object = QDoubleValidator `notationChanged` signal-instance cache; PySide6 6.8.1.x weakref use-after-free; upstream fix `e226b5827c` in 6.8.2; A/B 5/5 vs 0/5 | `m307_*` | ROOT CAUSE IDENTIFIED; fix = OWNER DECISION |
| M308 | D74 release policy | release only when PySide6 ≥ 6.8.2 and `DRILLMASTER_RETAIN_CLOSED_WINDOWS` ≠ 1 | `m307_m308_*.md`, `m308_*.txt` | PARTIALLY RESOLVED |
| M309 | D51 monitor | 0 watchdog events in the window | `m309_*` | NOT REPRODUCED |
| M310 | resource profile | no widget, thread, fd or temp-file leak in the new modules | `m310_resource_profile.md`, `.csv` | DONE (measurement) |
| **M311** | **M274** architecture revision diff | ADDED/REMOVED/CHANGED, geometry consequences, pinned cases; W3b button | `m311_m274_*.md` | IMPLEMENTED — PARTIALLY QUALIFIED |
| M312, M313 | M275, M276 (mutation-only items of M261–M290) | not re-implemented in this mission | – | unchanged: PARTIALLY RESOLVED |
| **M314** | **M277** DDR hydraulics check | recorded vs recomputed HSI/TFA; W2 dialog | `m314_m277_*.md` | IMPLEMENTED — PARTIALLY QUALIFIED (SCREENING) |
| M315, M316 | M278, M279 (mutation-only) | not re-implemented | – | unchanged: PARTIALLY RESOLVED |
| **M317** | **M280** cement job reconciliation | sacks × yield vs gauge annulus, displacement vs shoe capacity; W3b | `m317_m280_*.md` | IMPLEMENTED — PARTIALLY QUALIFIED (WORKSHEET) |
| **M318** | **M281** T&D friction sensitivity | declared factors, observation bracketed, never interpolated; W13 | `m318_m281_*.md` | IMPLEMENTED — PARTIALLY QUALIFIED (SCREENING) |
| M319 | M282, M283 (mutation-only; M283 TRAINING AID) | not re-implemented | – | unchanged |
| **M320 D** | **M287** Report Center section manifest | per-section status in every DDR/EOWR export's provenance; "Not recorded" statements | `m320d_m287_*.md` | IMPLEMENTED — PARTIALLY QUALIFIED |
| **M320 E** | **M288** answers with exact citations | JSON + md record, exact offline verification, two UI buttons | `m320e_m288_*.md` | IMPLEMENTED — PARTIALLY QUALIFIED |
| M320 A–I | final report, roadmap, matrix, inventory, register | this file; `DRILLMASTER_ENGINEERING_ROADMAP_M320.md`; `PRODUCT_CAPABILITY_MATRIX.md` and `M241_CAPABILITY_INVENTORY.md` (M291–M320 sections); register updated | – | DONE |

## Must-implement items: what a user can do now

* **M274, architecture revision diff (W3b › Architecture › Compare with previous).**
  * Shows each component as added, removed or changed, with old → new values. A value that became blank shows as
    "unknown", never 0.
  * Names the strings whose geometry changed, and lists the calculation cases pinned to the older revision. Those
    cases are not recalculated.
  * A revision that fails its SHA-256 check is refused.
* **M277, DDR hydraulics check (W2 › Hydraulics check).**
  * Compares the recorded HSI and TFA with `calc_bit_hydraulics` at the minimum and maximum recorded flow.
  * A missing input gives NOT_COMPUTED. When a report has two drilling-parameter rows, the check refuses to choose
    between them.
  * The result can be saved as a case linked to its source row.
* **M280, cement job reconciliation (W3b › Architecture › Reconcile recorded job).**
  * Pumped slurry is recorded sacks × declared yield (`ft3/sk` only) and is compared with the gauge annulus over
    the recorded TOC–BOC on a frozen architecture revision.
  * Displacement is checked against shoe-track capacity × 1.02.
  * Unknown depths stay unknown.
* **M281, T&D friction sensitivity (W13 › Weight).**
  * Re-runs the pinned T&D case for each declared friction factor (no default, at most 12).
  * An observed torque or pick-up is placed BELOW, BETWEEN or ABOVE the declared factors. No calibrated factor is
    ever produced.
* **M287, Report Center section manifest.**
  * Every DDR and EOWR export (HTML, PDF, Excel, CSV) now lists every template section as INCLUDED (with rows),
    NOT_RECORDED, SUMMARISED, QUERY_FAILED or NOT_RENDERED.
  * Empty sections say "Not recorded: no X data was submitted for this scope." Previously they were silently
    omitted.
  * No cost data is "not a reported zero". Time analysis without hours is "unknown, not 100 % productive".
* **M288, answers with citations (Knowledge Assistant › Export with citations… / Verify citation file…).**
  * A ready answer is frozen with the exact span, quote and page SHA-256 of every citation.
  * Verification reports EXACT, PAGE_CHANGED, SPAN_MISMATCH, PAGE_MISSING, DOCUMENT_MISSING or UNREADABLE. It never
    re-anchors.
  * The record keeps "Not semantically verified".

Calculation History lists the M314, M317 and M318 cases as **NOT REPRODUCIBLE (no contract for the method)**.
This is asserted by tests and is roadmap item E2. They are never shown as re-runnable.

## Regressions and gaps found during the mission (stated, not hidden)

1. **`registry()` guard.** It was pushed in `d57f5b2` and failed the Source gate on all legs. The repo-wide AST
   guard runs only in the full suite. Fixed in `2273aa4`; the guard tests now run before every push.
2. **Exception ceiling.** M308/M314/M317 added four unexplained silent handlers (87 > 83). Each now carries a
   `silent-ok` reason, and the ceiling was not raised.
3. **Density inventory.** M314 adds two uses of 7.48052 (the existing hydraulics divisor, through
   `MudProperties.mw_ppg`). The inventory was re-written with its tool, and P8 is untouched. A docstring that
   literally mentioned "7.48" was reworded so that the inventory counts uses, not prose.
4. **Windows-only layout regression (M320 E).** See section A. It was found by the Windows gate on `2273aa4`
   and fixed with a structural regression assertion.
5. **`ae016a7` has no 3.12/3.13 result.** Those legs were superseded by the next push.

## B. Capability catalogue

See `docs/engineering/PRODUCT_CAPABILITY_MATRIX.md` ("M291–M320 additions") and
`docs/engineering/M241_CAPABILITY_INVENTORY.md` ("M320 update").

## C. Roadmap

See `docs/engineering/DRILLMASTER_ENGINEERING_ROADMAP_M320.md`. The first items are:
* R1: owner decision on the PySide6 ≥ 6.8.2 pin;
* E1: a mutation catalogue for the M291–M320 modules;
* E2: history re-run contracts for M314/M317/M318.

## D. Owner decisions (none taken on the owner's behalf)

* **The PySide6 pin bump to ≥ 6.8.2 is OWNER DECISION REQUIRED.** It is the D63 fix and enables D74 release. The
  lock stays at `PySide6==6.8.1.1`; `requirements.txt` and `pyproject.toml` stay at `>=6.6,<7`.
* P1–P19 are unchanged (see `m292_residual_register.md`).

**UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**
