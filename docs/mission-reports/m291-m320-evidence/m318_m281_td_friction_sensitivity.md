# M318 (M281) — torque & drag friction-factor sensitivity

UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED. SYNTHETIC data only.

* `core/torque_drag_sensitivity.py` (method `m318.td_friction_sensitivity`). Label: "SCREENING —
  FRICTION-FACTOR SENSITIVITY — NOT A CALIBRATED FRICTION FACTOR".
* **Friction factors:**
  * `TorqueDragEngine.calculate` is re-run for each friction factor the user declares.
  * There is no default. Each factor must lie in [0, 1], at most 12 are allowed, and decimal commas are refused.
* **Locating an observation:** `locate` brackets an observed torque or pick-up between two declared factors
  (BELOW, BETWEEN, ABOVE, NOT_CHECKED). It **never interpolates** a "matching factor", because that would be a
  derived number with no validated method. A non-monotonic curve is reported as such.
* **Saving:** a case that stores the declared factors, the observations (a missing one is marked NOT_ENTERED) and
  each location.
* **Calculation History:** NOT REPRODUCIBLE (stated); this is asserted.
* **UI:** W13 › Weight › **Friction-factor sensitivity**. It runs on the last pinned T&D run.
* **Anchor:** 165.23 klbf.

**Tests:** `tests/test_m318_td_friction_sensitivity.py` has 14 tests (13 core + 1 UI), 0 failures. With
`test_m127`, 24 tests ran with 0 failures. Ruff is clean.

**Status:** COMPLETE for the synthetic scope; SCREENING.
