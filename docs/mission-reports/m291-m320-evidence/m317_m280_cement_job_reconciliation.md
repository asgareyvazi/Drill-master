# M317 (M280) — recorded cement job vs frozen architecture

UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED. SYNTHETIC data only.

* `core/cement_job_reconciliation.py` (method `m317.cement_job_reconciliation`). Label: "WORKSHEET — RECORDED
  CEMENT JOB VS ARCHITECTURE — NOT A CEMENT EVALUATION".
* **Volumes and checks:**
  * Pumped slurry = sacks × yield ÷ 5.6146. Only the declared unit `ft3/sk` is accepted; any other unit is
    refused, never guessed.
  * The gauge annulus over the recorded TOC–BOC uses `well_architecture.cement_annulus` on a frozen revision.
  * Recorded displacement is checked against shoe-track capacity × 1.02.
* **Unknowns:** an unknown TOC or BOC stays unknown and is never inferred. An unparseable recorded value counts as
  missing; the handlers are marked `silent-ok` with the reason.
* **Hand values (test anchors):** 109.81 bbl, ≈ 240.2 bbl and 102.41 bbl.
* **Saving:** creates a case linked to the `cement_reports` row. The cement report and the architecture revision
  stay byte-identical.
* **Calculation History:** lists the case as NOT REPRODUCIBLE (no contract for the method); this is asserted.
* **UI:** W3b › Architecture page › **Reconcile recorded job** / **Save**.
* **Constant inventory:** re-written. 5.6146 ft³/bbl gains one use, in this module.

**Tests:** `tests/test_m317_cement_job_reconciliation.py` has 14 tests (13 core + 1 UI), 0 failures. Together with
`test_m109` and `test_m89`, 32 tests ran with 0 failures. Ruff is clean.

**Status:** COMPLETE for the synthetic scope; WORKSHEET.
