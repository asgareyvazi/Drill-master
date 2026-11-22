# M314 (M277) — DDR hydraulics check (recorded vs recomputed bit hydraulics)

UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED. SYNTHETIC data only.

* `core/ddr_hydraulics_check.py` (method `m314.ddr_bit_hydraulics_check`, "M314 v1"). Scope label: "SCREENING —
  recorded vs recomputed bit hydraulics (not a hydraulics programme)".
* **Inputs:** the one `DrillingParameters` row of a saved DDR (two rows are refused; it never chooses between
  them), the recorded nozzles/TFA, and the recorded mud weight.
* **Method:**
  * `calc_bit_hydraulics` is recomputed at the minimum and maximum recorded flow.
  * Mud weight goes from pcf to ppg through `MudProperties.mw_ppg` (÷ 7.48052, as in the hydraulics engine).
    The P8 divisor decision is not touched.
* **Verdicts:**
  * HSI AGREES when it lies within [low·0.95, high·1.05].
  * TFA tolerance is 1 %.
  * A missing input gives NOT_COMPUTED, never 0.
* **Saving:** produces an immutable calculation case "DDR hydraulics check", with a source link to the
  `drilling_parameters` row.
* **Calculation History:** lists the case as **NOT REPRODUCIBLE: no contract for method
  'm314.ddr_bit_hydraulics_check'**. That is stated, not hidden: there is no history re-run adapter, and the
  check is re-run from the DDR.
* **UI:** W2 Daily Report › **Hydraulics check**, using `dialogs/ddr_hydraulics_check_dialog.py`. Missing values
  show as dashes and cannot be saved.

**Tests:** `tests/test_m314_ddr_hydraulics_check.py` has 16 tests, 0 failures. The save test now also asserts the
history row and the NOT_REPRODUCIBLE re-run verdict. Ruff is clean. The density inventory was re-written
(`density_constants_m192.json`: +2 uses of 7.48052 in this module, both the existing hydraulics divisor).

**Status:** COMPLETE for the synthetic scope; SCREENING.
