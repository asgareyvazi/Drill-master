# M483–M485: Owner decision packages E1c, E11 and E12

**PARTIAL — UNSIGNED — NOT RELEASE-APPROVED — NOT FIELD-ACCEPTED.**

These are decision packages only. **No behaviour was changed by M483–M485 and nothing here is a decision.** They use
the nine-field format of `M196_OWNER_DECISION_PACKAGES.md`. No owner decision P1–P19 is approved.

---

## E1c — Herschel-Bulkley parameter fit from Fann readings (M483)

1. **Decision:** Whether DrillMaster may fit τ0, K and n from typed Fann readings, by which method, and who approves
   the method (P12).
2. **Current behaviour:** Fitting is **DISABLED**. `core/mud_engineering.py` reports `HB_STATUS` "NOT ASSESSED — this
   build has no validated Herschel-Bulkley fit". M416 (`m416.hb_slot_annulus`) and M420 accept only declared τ0, K and
   n, and never default them.
3. **Evidence:** the `HB_STATUS` text in `core/mud_engineering.py`; the R-HYD-2 spec, §6 "The HB fit from Fann
   readings is not part of this method"; roadmap item E1c.
4. **Licence / legal facts:** none for an own-code fit. API RP 13D text and tables are not licensed in this
   repository and are not reproduced.
5. **Options:**
   - (a) Keep the fit disabled; users declare τ0, K and n from a lab report.
   - (b) An own-code least-squares fit (for example τ0 bounded by θ3, then log-linear K and n), clearly labelled
     SCREENING, with its residuals shown and refused when the readings are non-monotonic.
   - (c) A licensed reference implementation or standard procedure, which needs a licence decision.
6. **Consequences:**
   - (b) makes the HB inputs derived values. Every M416 and M420 case would then need to record that its inputs were
     fitted, not declared, and the fitted values would need their own method ID and replay.
   - (c) needs P12 and possibly a new licence row.
7. **Engineering view:** (a) until a primary reference and a validation data set with data rights exist. Then (b),
   under its own method ID.
8. **Until decided:** DISABLED. M416 and M420 take declared values only.
9. **Owner must provide:** the reference procedure, an approver (P12) and a validation data set with rights.

## E11 — `BL-SS-CONSOLIDATE`: one surge / swab method in the UI (M484)

1. **Decision:** Whether the legacy W13 surge screening and the M420 service should stay side by side, and if not,
   which one remains and how old results are treated.
2. **Current behaviour:** Two methods coexist.
   - The legacy W13 screening (`core/hydraulics_engine.py`) uses a fixed 0.45 clinging factor and is labelled
     "Screening approximation".
   - M420 (`m420.surge_swab`) is quasi-steady and closed-end only. Its clinging constant K_c is declared and never
     defaulted, and an open-ended string is NOT ASSESSED.
   - Both keep their replay.
3. **Evidence:** `core/hydraulics_engine.py` (the 0.45 text); `core/surge_swab.py`; M196 "M460 status"
   `BL-SS-CONSOLIDATE`; roadmap E8b and E11.
4. **Licence / legal facts:** none.
5. **Options:**
   - (a) Keep both, with labels (current).
   - (b) Hide the legacy entry point and keep its stored results replayable.
   - (c) Remove the legacy method after a migration note.
6. **Consequences:**
   - (b) and (c) change what users see. Earlier legacy numbers are not reproduced by M420, because the clinging
     constant differs and is now declared.
   - (c) breaks the "preserve legacy surge with replay" rule unless the replay adapter is kept.
7. **Engineering view:** (b), but only after the open-ended case (E8b) is validated. Until then, (a).
8. **Until decided:** both methods unchanged. **No UI or behaviour change in M461–M520.**
9. **Owner must provide:** the product decision and the wording for users.

## E12 — `BL-BIT-DEFAULTS` (M485)

1. **Decision:** Whether two documented defaults in `core/engineering/engines/bit_performance.py` should become
   required inputs.
2. **Current behaviour:**
   - `d_exponent_corrected` uses a normal mud-weight baseline of 8.6 ppg when none is given. The note "Normal mud
     weight baseline 8.6 ppg unless provided" is returned with the result.
   - `cost_per_foot` without rotating hours returns the trip-only cost, (C_rig × T_trip + C_bit) / footage. With
     rotating hours it uses the full cycle.
3. **Evidence:** the `bit_performance.py` docstrings and returned notes; mutants BP-* in `mutation_m261_m290.py`,
   7/7 killed again in M473; M196 "M460 status" `BL-BIT-DEFAULTS`.
4. **Licence / legal facts:** none.
5. **Options:**
   - (a) Keep both defaults, documented (current).
   - (b) Require both inputs: a missing value gives NOT ASSESSED.
   - (c) Keep the defaults but return a structured "ASSUMED" class next to the value.
6. **Consequences:**
   - (b) changes results for existing callers and history: old records would replay differently. It would need a new
     method version.
   - (c) is additive.
7. **Engineering view:** (c) first, then (b) under a new version if the owner wants strictness.
8. **Until decided:** unchanged. **No behaviour change in M461–M520.**
9. **Owner must provide:** the choice, and for (b) the migration rule for stored results.
