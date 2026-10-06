# M40 — Safety-Critical Engineering Hardening, Canonical Hydraulics, Numerical Integrity & Engineering Truthfulness

**Audit date:** 2026-10-06

**Purpose:** Record the implementation boundary, numerical derivations, regression evidence, and unresolved release gates for the M40 engineering-hardening work. This document is not a standards-compliance certification, field validation, or operator acceptance.

## Scope and inventory

Reviewed the current engineering architecture/capability/audit/reference-matrix documents, canonical hydraulic and well-control engines, extended compatibility APIs, W13 hydraulics/bit/rheology/kill-sheet paths, kill-sheet persistence, pipe/casing/nozzle dialogs, and their direct tests. Caller searches covered `calc_surge_swab`, `WellControlExtended.kick_tolerance`, canonical bit/TFA APIs, and the extended Bingham wrappers. The kill-sheet persistence layer was reviewed together with its schema-version and cross-process regressions.

Canonical calculation owners remain in `core/hydraulics_engine.py`, `core/engineering/core.py`, and `core/engineering/engines/well_control.py`. W13 and compatibility wrappers delegate to these owners. Formula checks were performed against independently evaluated field-unit expressions and the named source context below; no claim of API/IWCF compliance is made from these comparisons.

## Mathematical and unit checks

### Fann rheology

For explicit Fann dial readings at 600 and 300 rpm:

- `PV [cP] = theta600 - theta300`
- `YP [lbf/100 ft²] = theta300 - PV`
- `n = 3.32 log10(theta600/theta300)`
- `K = 510 theta300 / 511^n` under the cited equivalent-cP field convention.

The `K` convention is not a dimensional SI consistency index. The `max(0, 2 theta3 - theta6)` yield estimate requires both low-speed readings and is screening-only. `PV + 5 YP` is named and labeled a heuristic indicator, not a constitutive viscosity. Non-finite/negative dial readings and internally negative Bingham YP are rejected.

### Bingham pressure loss and velocity

The simplified field-unit laminar components remain single-sourced in the canonical hydraulics engine:

- Pipe: `PV V L /(1500 D²) + YP L /(225 D)` psi.
- Concentric annulus: `PV V L /(1000 gap²) + YP L /(200 gap)` psi.

`PV` is cP, `YP` is lbf/100 ft², `V` is ft/s, `L` is ft, and diameters/gap are inches. Independent zero-yield comparisons convert to SI Hagen–Poiseuille pressure loss; the returned model scope remains screening. Extended pipe/annulus wrappers now compute velocity in canonical ft/s, select the canonical laminar/turbulent branch, and state scope and limitations.

Bit hydraulics use the canonical field equations `ΔP = Q² MW /(10858 TFA²)`, `HHP = Q ΔP/1714`, `HSI = HHP/(π OD²/4)`, `Vjet = Q/(3.117 TFA)`, and `IF = MW Q Vjet/1930`. `BitEngine.calculate_tfa` rejects absent, non-finite, non-positive, boolean, or malformed nozzle sizes instead of ignoring them.

### Surge/swab

The implementation requires explicit positive trip speed, operation, open/closed pipe selection, a complete drill-string program, explicit bore intervals with positive clearance, and TVD support. It applies the stated displacement relation and the selected maximum-velocity factor in ft/min, then converts to ft/s and delegates the pressure loss to the canonical annular rheology branches. Piecewise intervals and the open-pipe displacement area are tested independently. The clinging-factor and maximum-velocity choices are screening assumptions, not a standards guarantee. The previously considered shear-rate multiplier with ambiguous source-unit conventions is not used.

### Well control and kill-sheet geometry

LOT surface-pressure conversion is `fracture MW = current MW + LOT pressure/(0.052 × shoe TVD)`. A legacy influx gradient in ppg-equivalent units is explicitly converted to psi/ft; passing both conventions or invalid legacy values returns `NOT_ASSESSED`/`INVALID_INPUT`. The compatibility kick-tolerance adapter delegates to `WellControlEngine` and does not manufacture influx or capacity inputs.

Kill-sheet annular volume now requires a pipe program reaching measured depth, explicit shoe MD, casing ID, open-hole size, and positive clearances in every used interval. TVD is not treated as shoe MD on a directional well. Missing shoe MD or incomplete pipe length leaves geometry-derived totals and strokes unknown. Kick-height screening is only emitted when the required geometry exists and is labeled as a uniform-bottomhole-capacity approximation; it is not a multi-interval influx simulation. Snapshot schema version 3 includes shoe MD in the persisted input identity.

## W13 and missing-input behavior

- Hydraulics outputs and chart/table values are cleared on input edits, unconfirmed display seeds, and failed recalculation. Export/print require a current assessed result.
- Bit nozzle TFA and calculations delegate to canonical engines. Nozzle geometry is not prepopulated; a valid explicit size/count is required. Bit and MSE results are cleared when their inputs change, and MSE remains independently calculated.
- Pipe and casing dialogs no longer treat a prefilled 5-in drill pipe or 9-5/8-in casing as measured geometry. New rows require positive dimensions and interval length before acceptance; calculated preview fields are cleared or marked unassessed when dimensions are invalid.
- Kill-sheet results, save eligibility, and cached inputs are invalidated on changes to well, pipe, mud, kick, pump, or method inputs.

## Evidence

Independent numerical regressions live in `tests/test_hydraulics_m40_regressions.py`; public compatibility and engine regressions are in `tests/test_extended_engineering.py`, `tests/test_engineering_ground_truth.py`, `tests/test_well_control_kill_sheet.py`, persistence/cross-process tests, and the W13/single-source guards. The most recent focused run reported **263 passed** across hydraulics, well control, kill-sheet, compatibility, W13/headless, nozzle-optimization, integration, documentation, M36/P6 preservation, and single-source regression suites. Syntax compilation passed for all `core`, `tabs`, `dialogs`, and `tests` Python modules. A build of both the wheel and source distribution completed successfully, and the tracked runtime-import-closure check passed.

A full collection attempt could not collect 18 Qt-dependent test modules because the runner lacks the system `libGL.so.1` library. A wider non-GUI run recorded 1,774 passing tests, 44 skips, and failures dominated by that same missing library; it also exposed stale assertions expecting numeric zero on invalid W13 inputs, which have since been strengthened to expect validation errors. The missing system library also prevents local entrypoint/widget package-smoke acceptance. Fresh full pytest in CI with real Qt system libraries remains necessary.

## External acceptance and release status

This source audit does **not** establish Windows packaging/installer behavior, clean-machine installation, real PDF/MinerU integration, production database migration, operator sign-off, or exact-SHA CI. Fresh full pytest with real Qt system libraries, release smoke, compile/lint/package checks, clean worktree verification, push, remote-SHA verification, and fresh exact-SHA Python 3.11/3.12/3.13 Source CI remain release gates. Historical M36/P6 evidence and owner decisions are outside this change's authority and must not be rewritten or inferred.

## References

- Boyun Guo and Gefei Liu, “Mud Hydraulics Fundamentals,” *Applied Drilling Circulation Systems: Hydraulics, Calculations, and Models* (2011), Chapter 2, pp. 19–59, DOI `10.1016/B978-0-12-381957-4.00002-4`; field-unit rheology/Bingham formula context, not a compliance basis.
- Maurer Engineering Inc., *Wellbore Hydraulics Model (HYDMOD3): Theory and User’s Manual*, DEA 67 Phase II, October 1996, TR96-39, Section 2.2; secondary context for displacement-based surge/swab approximation and the stated factors, not a compliance basis.
- Public reference URLs recorded in the M40 session notes: `https://www.sciencedirect.com/topics/engineering/mud-hydraulics`, `https://www.sciencedirect.com/topics/engineering/power-law-fluid`, and BSEE-hosted HYDMOD3 PDF `https://www.bsee.gov/sites/bsee.gov/files/tap-technical-assessment-program//300ad.pdf`.
