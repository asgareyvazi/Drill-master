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

## Addendum (M43 release hardening, 2026-10-20)

A re-audit found that real equipment (bit) serial numbers from the same
workbook had survived in three files of this directory:
`evidence/golden-a.json`, `evidence/followup/golden-a-import.json` and
`evidence/followup/golden-a-lifecycle.json` (`serial no` / `serial_number`
fields). Their digits were replaced by the marker `[REDACTED:serial]`:
24 occurrences of 4 distinct values, 8 per file; nothing else in these files
was changed and each file still parses. As above, any SHA-256 recorded for
these files before 2026-10-20 describes the earlier version, and the earlier
versions remain in Git history until the owner-approved purge
(`docs/privacy/HISTORY_PURGE_PLAN.md`, which now lists them) is carried out.
