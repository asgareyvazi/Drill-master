# M311 (M274) — component-level comparison of architecture revisions

UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED. SYNTHETIC data only.

**What changed**
* `core/architecture_diff.py` (`DIFF_VERSION` "M311 architecture revision diff v1"). It is read-only.
* Matching: components are matched by `(kind, name)`. When an identity repeats, matching follows stored order,
  and a note says so.
* Each identity gets a status: ADDED, REMOVED, CHANGED (every changed field, old → new) or UNCHANGED. A change of
  library binding fingerprint also counts as a change.
* Blank stays None and is shown as "unknown". A value that becomes unknown is a change; it never becomes 0.
* Loading uses `well_architecture.get_revision`, so a revision that fails its SHA-256 check is refused, never
  compared.
* Refused comparisons: revisions from different wells, or the same revision twice. The two revisions are
  ordered by revision number whatever the argument order.
* Consequences are stated, never recalculated:
  * strings and cement whose geometry changed (top, bottom, OD, ID, hole);
  * calculation cases pinned (`architecture_revision_id`) to the older revision.
* UI: W3b schematic › Architecture page › **Compare with previous**. It is enabled only when an older revision
  exists, and the result appears in the panel status line.

**Tests:** `tests/test_m311_architecture_diff.py` has 6 tests, 0 failures. They cover:
* the identical case;
* changed, added and removed components, plus value → unknown;
* duplicate identities;
* ordering, the pinned-case list and the different-well refusal;
* a tampered revision refused by SHA-256;
* the panel button.
They ran together with `test_m317`: 20 tests, 0 failures. Ruff is clean.

**Status:** COMPLETE for the synthetic scope.
