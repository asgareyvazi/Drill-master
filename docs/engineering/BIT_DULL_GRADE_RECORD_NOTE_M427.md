# Bit dull grade — IADC record, validation and trend (M427 note)

Status: **IMPLEMENTED — RECORD ONLY — NOT APPROVED — OWNER REVIEW REQUIRED.**

- Method: `m427.bit_dull_grade`, version `M427 IADC dull grade record v1`.
- Module: `core/bit_dull_grade.py`.
- UI: W13 Bit/MSE page button **🦷 Bit dull grade (IADC)…**, through `EngineeringServiceDialog`.
- Persistence: a calculation case, written with `core/calculation_cases.save_case`. Replay goes through `core/history_replay.SERVICE_MODULES`.
- Catalogue: `core/method_catalogue._case_services`.

## What it is

The module is a structured record of the eight IADC dull-grade fields, written I-O-D-L-B-G-O-R, as graded by the user. It does three things:

- **Validation.** Each field is checked against the code set stored in the module:
  - inner and outer rows use integers 0–8;
  - dull characteristic and other characteristic use the two-letter codes in `DULL_CODES`;
  - location codes depend on the bit type;
  - bearings are E/F/N or 0–8 on a roller-cone bit, and X on a fixed-cutter bit;
  - gauge is I, or 1–16 sixteenths of an inch;
  - reason pulled uses `REASON_CODES`.
- **Bit-type gating.**
  - Roller-cone-only codes (`CONE_ONLY`) are refused on a fixed-cutter bit.
  - Fixed-cutter-only codes (`FIXED_CUTTER_ONLY`) are refused on a roller-cone bit.
- **Per-well trend.** The trend lists the saved VALID grades of one well, ordered by depth out, then by date out, then by save order. It uses ordering and footage arithmetic (depth out − depth in) only.

Code sources: the IADC roller-bit dull grading system (1987 revision) and the IADC fixed-cutter dull grading system (first revision, SPE/IADC 23939, 1992). These are public classification facts. The module accepts only codes it stores. An unknown code is refused and never mapped to a near match.

## Outcomes

| Status | When |
|---|---|
| NOT ASSESSED | A required field is empty. The missing fields are listed. No value is ever substituted for an empty field (the dialog sends `None`, which mutant `DLG-empty-is-zero` checks). |
| INVALID | Every problem is listed: out-of-range scale, unknown code, a code not allowed for the bit type, depth out < depth in, or a bad date format. INVALID results cannot be saved. |
| VALID | The grade string, for example `1-2-WT-S-X-I-CT-TD`, and the footage when both depths are given. |

- A save without a well is refused.
- Trend rows that have no depth out sort last.

## Explicitly not implemented

- **Remaining-life or wear-rate prediction.** A predictor needs a validated dull-grade dataset (formation, operating parameters, run outcomes) under usable data rights, plus a published method. Neither is in the repository. This is tracked as roadmap item N-BIT-1 in `DRILLMASTER_ENGINEERING_ROADMAP_M460.md`.
- **No inference from DDR rows.** The M130 bit-run aggregation states that DDR rows carry no dull grade.
- **No link from a grade to bit-run KPIs.** Footage-weighted ROP and cost per foot stay in `engine.bit_performance`. The open defaults question is tracked as `BL-BIT-DEFAULTS`.

## Verification (SYNTHETIC)

- Tests: `tests/test_m415_m427_engineering_services.py`. They cover:
  - valid fixed-cutter and roller-cone grades;
  - each refusal class;
  - a None-safe evaluation (this regression fixed a crash);
  - save and replay;
  - trend order when a shallow case is saved before a deep one;
  - the dialog.
- Mutation: `tools/quality/mutation_m401_m460.py` mutants DG-cone-code-on-pdc, DG-scale-9-accepted, DG-no-well-saved and DG-trend-unordered. All are killed in run 2 (`docs/mission-reports/m401-m460-evidence/m401_m460_mutation_run2.txt`).
- Scope: all inputs are synthetic and no field dull-grade data was used. Classification: **VERIFIED COMPLETE FOR STATED SYNTHETIC SCOPE** (a record and validator, not an engineering prediction).
