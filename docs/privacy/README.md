# Data privacy in the DrillMaster repository

This repository is **public**. It must never contain real operational records:
daily drilling reports, personnel names, exact well coordinates, credentials,
production databases or personal paths.

## Classification used for remediation (M43)

| Tier | Content | Rule |
|---|---|---|
| 1 — personal / precise | personnel names, user-profile paths, e-mail addresses of real people, exact well coordinates, credentials, real DDR files, embedded logos/photos, printer/device names | must not exist in the current tree; enforced by `tools/privacy/privacy_check.py` |
| 2 — operational identifiers | well name, field code, rig number, client and contractor names of a specific operation | removed from fixtures and shipped package data; still mentioned by name in older audit reports (see "Remaining exposure") |
| 3 — public / technical | formation and oil-field names, public company template anchors (`OEOC Rig`, `Client (KPE)`, `MSA` POB labels used by `templates/OEOC_DDR_v3.json`), vendor brands, depths, mud properties, BHA, chemicals, activity codes | allowed |

## What M43 found and changed

| Finding | Evidence (no values reproduced) | Action |
|---|---|---|
| A real daily drilling report was committed at the repository root (`08-DDR …xlsx`) | 9 personnel cells (client representative, supervisors, superintendent, manager, geologist, tool pusher), exact northing/easting and the same as text, well/field/rig identity, client name, bit serials, 7 embedded images, printer settings | removed from the tree; replaced by `tests/fixtures/synthetic_ddr_golden_a.xlsx` |
| A full cell-by-cell dump of that report is **shipped in every wheel and installer** (`templates/OEOC_DDR_full_extraction.json`, listed in `pyproject.toml` and `packaging/DrillMaster.spec`) | the same personnel names and coordinates | replaced in place by the de-identified dump; no runtime code reads it (only packaging lists it) |
| Coordinates copied into historical audit evidence | 58 occurrences in 7 files under `docs/` | replaced by `[REDACTED:northing]` / `[REDACTED:easting]` (see `docs/audits/2026-09-08-ddr/REDACTION_NOTICE.md`) |
| A personal Windows profile path in a usage example | `tools/mineru_integration.py` | replaced by `$env:USERPROFILE` |
| A real coordinate used as a format example in a code comment | `core/canonical_mapper.py` | replaced by a synthetic value of the same shape |
| **Found in the release-hardening re-audit (2026-10-20):** real bit serial numbers survived the first pass — as text in three evidence JSONs, and as numeric cells in the shipped dump and in the "de-identified" fixture (the first sanitization pass handled text and coordinate cells, not these numeric cells) | 4 distinct values; 24 text occurrences in 3 evidence files; 2 numeric cells (`DDR Data!N52:N53`) in each of the dump and the fixture | text replaced by `[REDACTED:serial]`; numeric cells overwritten with synthetic values by the same sanitizer; digests added to the denylist; new `equipment-serial-number` rule (see `PRIVACY_CHECK.md`) |

No credentials, tokens or private keys were found in the tracked tree
(pattern scan in `tools/privacy/policy.json`). E-mail addresses present are
GitHub noreply or demo addresses.

### How the synthetic fixture was made

`tools/privacy/sanitize_ddr_workbook.py` works on the OOXML parts, so formulas
**and** their cached results, merged ranges, styles, the hidden sheet, tables,
charts and data validations are preserved. Identity strings are substituted
everywhere they occur (shared strings, cached formula strings, chart caches,
document properties); numeric coordinate cells are overwritten; images are
blanked at the same size; printer-settings parts are dropped. The tool
re-opens its own output and fails if any protected token survives in any part.
The substitution spec is **private** and is not in the repository; its format
is shown in [`ddr_sanitization_spec.example.json`](ddr_sanitization_spec.example.json).

Equivalence was verified before the swap:

- `ExcelIntelligence` with `templates/OEOC_DDR_v3.json`: identical canonical
  structure (3,468 leaf paths), the same 136 fields, 17 tables and 147 rows; the
  only differing values are the 17 substituted identity fields;
- the seven test modules that used the real workbook: 249 passed before and
  249 passed after, test for test; only assertions on substituted identity
  values were changed (for example the well name `SYNW-101`).

## Remaining exposure — owner action required

**The public default branch still serves the real workbook.** `drill-Master`
(tip `e3fa42a`) never received the M43 remediation; its current tree contains
the workbook and 11 other protected blobs. Merging the remediation into the
default branch is an ordinary commit (no rewrite) but an owner action — see
section 0 of [`HISTORY_PURGE_PLAN.md`](HISTORY_PURGE_PLAN.md). Until then the
privacy score for "current tree" applies to the M43 working branch only.

**A normal commit does not remove anything from Git history.** The original
workbook, the unsanitized dump and the evidence files remain in every earlier
commit on all branches of this public repository (introduced in commit
`7589803dab65`, 2026-08-29), and may exist in clones, caches and pull-request
refs. Purging them requires a history rewrite, which is owner-gated; the
reviewed procedure is in [`HISTORY_PURGE_PLAN.md`](HISTORY_PURGE_PLAN.md) and has
**not** been executed.

Tier-2 identifiers (the well, field, rig and client names of that operation and
the original file name) still appear as plain references in historical audit
reports under `docs/`. Whether to scrub those as well is an owner decision; it
does not affect the code.

## Rules for contributors

- Never commit a real DDR, PDF, database or screenshot of real data. Use
  `tests/create_fixtures.py` or the sanitizer.
- Every binary data file must be added to `allowlisted_data_files` in
  `tools/privacy/policy.json` with its SHA-256 and provenance, after review.
- Run `python tools/privacy/privacy_check.py` before pushing; the same check
  runs in the test suite (`tests/test_privacy_check.py`).
- Do not upload real DDRs to third-party services or external model APIs.

See [`PRIVACY_CHECK.md`](PRIVACY_CHECK.md) for the rule reference.
