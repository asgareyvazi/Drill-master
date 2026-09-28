# ReviewItem certification audit — 2026-09-08

## Scope and authority

This report is the real-workbook audit for the repository DDR fixture. It uses
the production Excel route and an isolated in-memory SQLite database; it does
not modify a user production database. The complete machine-readable artifact
is [`review_audit_2026-09.json`](review_audit_2026-09.json).

The artifact retains the repaired pre-change **79-item baseline** for
explosion/disappearance comparison and the authoritative corrected result. A
ReviewItem was not removed merely because it was inconvenient: deterministic
preferred-cell mappings are now accepted by the confidence policy, while
ambiguous, malformed, missing-required, continuation, survey-angle, and BOP
values remain reviewable with their source tokens.

## Corrected result

| Check | Result |
| --- | ---: |
| Import status | `REVIEW_REQUIRED` |
| Imported rows | 101 |
| Failed rows | 0 |
| Persistence validation errors | 0 |
| Current ReviewItems | 72 |
| Missing provenance/core fields | 0 |
| Duplicate ReviewItem keys | 0 |
| Extractor source-shape fields | 141 |
| Extractor tables / rows / rejected rows | 17 / 147 / 14 |
| Canonical typed/bounds validation | valid |

The current 72 rows are the complete review output after correction. The
baseline 79 rows remain in the JSON artifact so a later run can detect
explosions, disappearances, or silent acceptance rather than comparing only a
count.

Current audit categories from the production persistence result are:

| Category | Count | Treatment |
| --- | ---: | --- |
| time-log issue | 35 | retain invalid/missing anchors; never invent times |
| survey ambiguity | 3 | retain nullable azimuth; never invent an angle |
| BOP ambiguity | 2 | retain missing component type/required values |
| continuation row | 2 | retain text without inventing an independent time range |
| missing required value | 2 | retain source row and full cell map |
| mapping conflict | 1 | retain competing canonical candidates |
| other | 27 | retain invalid tokens, unresolved optional/ambiguous fields |

The audit harness reports no missing provenance/core fields. Persistence rows
now carry file, sheet, source row, table, and the complete source-cell map;
field rows carry the exact Excel cell, canonical entity/field, expected type,
mapping method, reason, and normalized/source values.

## Corrected findings that must remain visible

- `well_info.water_depth` is anchored to `AQ6` (`-`) and remains NULL plus a
  reviewable placeholder. The previous diagonal `AM11` casing-size value is
  no longer accepted as water depth.
- `well_info.latitude` retains `3,441,012 N` as a malformed coordinate token;
  the `N` suffix is not silently converted into a float.
- `well_info.longitude` retains its nonnumeric source token.
- Note anchors with no independent value remain unresolved at their configured
  source cells; fuzzy text from a neighboring note is not substituted.
- Lookahead rows 21–22, BOP row 80, continuation rows, and survey rows 58–60
  retain source locations and review reasons.
- Four same-value scalar mappings are recorded in the artifact as
  `DUPLICATE_CONFIRMED` / `duplicate-same-value` provenance. They are not
  conflicts and are not silently discarded.

## Reproduction commands

From the repository root, with the dependency-complete environment:

```bash
PYTHONPATH=. python -m pytest -q tests/test_review_contract_certification.py
PYTHONPATH=. python -m pytest -q tests/test_mineru_engine.py tests/test_import_quality_extra.py
PYTHONPATH=. python -m compileall -q core dialogs tabs tests
```

The temporary real-route audit used for this certification is intentionally
kept outside the repository and writes only to an isolated SQLite database.
The committed golden tests cover the source shape, canonical semantic
validation, ReviewItem lineage, duplicate classification, formula/cached-value
regressions, and PDF unit safety.
