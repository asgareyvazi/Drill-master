# Redaction notice (M43, 2026-10-19)

Exact well coordinates (northing and easting, as text and as numbers) taken
from the original Golden A workbook were replaced in this directory's evidence
files — and in `docs/review_audit_2026-09.json` and
`docs/REVIEW_AUDIT_2026-09.md` — by the markers `[REDACTED:northing]` and
`[REDACTED:easting]`. 58 occurrences in 7 files were replaced; nothing else in
these files was changed. Each JSON file still parses.

These are historical records: the markers are deliberately not plausible
values, so no record now asserts a coordinate that was never observed. The
redaction changes the files' bytes, so any SHA-256 recorded for them before
2026-10-19 describes the pre-redaction version.

The original workbook these records were produced from is no longer in the
current tree; tests use `tests/fixtures/synthetic_ddr_golden_a.xlsx`. The
pre-redaction versions remain in Git history until the owner-approved purge in
`docs/privacy/HISTORY_PURGE_PLAN.md` is carried out. See `docs/privacy/README.md`.
