# M322 – independent audit of M291–M320

**UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**

**Method.** I read the M291–M320 report, the M320 roadmap, the matrix and inventory sections, the residual
register and every M291–M320 evidence file. Each claim was then re-checked against the code at `6754e14`: the
production module, the UI call site, which selected record is used, how persistence happens, and what the tests
actually drive. The reports were not taken as evidence.

## Summary

| Area | Code present | UI calls it | Selected record used | Persistence / provenance | Tests drive the production path | Audit class |
|---|---|---|---|---|---|---|
| M274 / M311 architecture diff | yes | yes (W3b "Compare with previous") | the selected revision against the next older one | read-only | yes (panel button) | **defect A-1**: pinned work misses casing runs |
| M277 / M314 DDR hydraulics check | yes | yes (W2 dialog for the open report) | yes; two drilling-parameter rows are refused | case with source link | yes | **gap A-5**: history replay missing |
| M280 / M317 cement reconciliation | yes | yes (W3b Architecture) | yes; a revision from another well is refused | case with source link | yes | **defects A-2, A-3, A-4** |
| M281 / M318 T&D sensitivity | yes | yes (W13 Weight, last pinned run) | the last T&D run in the tab | case | yes | **defect A-6**: the saved case cannot be replayed |
| M287 / M320 D section manifest | yes | yes (every DDR/EOWR export) | report scope | in the provenance | yes | **gap A-7**: NPT / Cost / Plan have no manifest |
| M288 / M320 E citation record | yes | yes (Knowledge Assistant) | the shown answer | JSON + md file | yes | **gap A-8**: no navigation from a record to the passage |
| M307–M310 reliability | yes | release policy in MainWindow | – | – | policy tests and the probe | as reported. D63/D74 stay owner-gated (pin) |
| M303–M306 clone contracts | yes | workbench | yes | `clone_of` links, audit | yes | as reported. D87 equal-timestamp case still open |
| M295–M302 value states and lineage | yes | W2, import review | yes | events | yes | as reported |

## Findings

### A-1 (M311): pinned work misses `casing_calculations`

`architecture_diff._pinned_cases` scans only `calculation_cases`. A casing-design run (`casing_calculations`)
that used the older revision is not listed, so the claim that "saved work pinned to the older revision is listed"
is only partly true. The product already has the canonical lookup, `calculation_history._architecture_users`, which
covers both tables. Severity: medium (an information gap, not a wrong number).

### A-2 (M280 / M317 input path): the new cement report form stores invented defaults (**D89**)

`tabs/w3c_section_data.CementReportTab.clear_form()` fills placeholders: slurry density 120, yield **1.18**, mix
water 5.2, compressive strength 2,500, thickening 04:30, and 0 for sacks, displacement, **TOC** and BOC.

The "preserve untouched NULL" mechanism (`preserve_widget_values`) only protects values that were *loaded*. On a
new report the source map is empty, so the placeholders are saved as recorded data. As a result:
* a never-entered yield of 1.18 produces an M317 pumped volume;
* a never-entered TOC = 0 is treated as cement to surface.

`CasingReportTab` has the same pattern: burst, collapse, tension, torque, drift and so on are saved as 0.

This breaks "never turn missing into zero / never guess cement yield". Severity: **high**, because it feeds an
engineering worksheet.

### A-3 (M317): "CONSISTENT" overstates the displacement check

The check is one-sided: it is EXCEEDS_CAPACITY only above string capacity × 1.02, and anything lower reads
"CONSISTENT". A recorded 10 bbl against a 100 bbl capacity would therefore be called consistent. Because the shoe
track is not recorded, capacity to the shoe is only an *upper bound*, so under-displacement cannot be judged at
all. The honest state is WITHIN_UPPER_BOUND. Severity: medium (a misleading label).

### A-4 (M317): a recorded zero is reported as "not recorded"

`_num` maps 0 sacks or 0 yield to None, and the note then says "sacks and slurry yield must both be recorded". The
value *was* recorded, as 0. The volume must still not be computed, but the note must say why. Severity: low.

### A-5 (M314, M317, M318): no history replay

Calculation History lists these cases as NOT REPRODUCIBLE. The reports state this honestly; it is closed by M328.

### A-6 (M318): the saved case cannot be replayed

`torque_drag_sensitivity.save_case` stores the factors, mud density, WOB, hole ID and survey revision id. It does
**not** store the survey stations, the survey SHA-256 or the string components. Replay would have to re-read
mutable W13 state, which the mission forbids. A pin of `None` (an unpinned survey) is stored silently. Severity:
medium. Closed by M328 with a full snapshot.

### A-7 (M320 D): NPT, Cost and Plan reports have no manifest

These reports state that no manifest is available. That is stated rather than hidden, but incomplete. Closed by
M333.

### A-8 (M320 E): no navigation from a citation record

A saved record can be verified, but the cited passage cannot be opened from the record. Closed by M334.

### A-9 (process): Windows-only layout regression

M320 E broke a Windows minimum-width test that offscreen Linux fonts cannot reproduce. M320 fixed it and added a
structural assertion. A general mitigation is in the M352 pre-push guard (a large-font layout probe of the panels
changed in a commit).

## Status claims

* "COMPLETE for the synthetic scope" in the M311, M314, M317 and M318 evidence files conflicts with the M320
  vocabulary (IMPLEMENTED — PARTIALLY QUALIFIED). The capability matrix uses the right label. The evidence files
  are corrected by the M323 register (states only; the history is kept).
* The M320 roadmap and matrix match the code.
* No claim of QUALIFIED was found for M291–M320 modules.
