# P6 p6-batch-005 — class mixed HIGH - C:37, D:8 (kill-sheet canonical inputs 26 records / 13 statements, time parsing 6, calculator wrappers 6, hydraulics 2, inventory semantics 2, report loaders 2, one test oracle)

records **45** over **29** sites · DUPLICATE/FALSE-POSITIVE: 21 · VERIFIED-CORRECT: 15 · INTENTIONAL: 8 · GENUINE_DEFECT: 1

## Defects fixed

- INV34-001751 / INV34-007524 - core/engineering/well_control_kill_sheet.py:290 (`casing_id_in=_num(casing_id_in) or 0.0`): a required, consumed input was missing from the builder's required_raw gate, so an unfilled casing-ID field (the widget sentinel reads back as None) silently removed the annular volume - and the annular displacement strokes derived from it - from a sheet that still reported success. Fixed in ff2000a; regression tests/test_kill_sheet_casing_id_gate.py (mutation-killed: reverting the gate yields 'assert () == ("casing_id_in",)', a truthiness-based gate also fails). One statement, one defect, two register records.

## INV34-001751 — `core/engineering/well_control_kill_sheet.py:290`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** GENUINE DEFECT, found here and fixed in this batch's code commit ff2000a. ``casing_id_in`` is a *required* keyword of the builder (no default, 215) and it IS consumed - ``csg_id = inp.casing_id_in`` (454) feeds the annular loop (475-479) - yet it was the one consumed input missing from ``required_raw`` while the comment above that gate claims to list exactly the consumed inputs (257). The widgets hand the builder None for their not-supplied sentinel ("Read a kill-sheet input; the sentinel reads back as ``None``", tabs/w13_Engineering_Calculator.py:5227-5231), so the None case is real. An unfilled casing-ID field therefore became 0.0: ``ann_id_val > od`` is false, no annular volume (and no annular displacement strokes derived from it) is produced, and the sheet still reports ``success=True`` - the fabricated-but-plausible answer the module's own refusal exists to prevent (436-443). Fix: add the input to the gate; an explicit 0.0 remains a supplied value.
- **Classification:** GENUINE_DEFECT
- **Defect:** yes
- **Test:** tests/test_kill_sheet_casing_id_gate.py (3 tests; mutation-validated)
- **Commit:** ff2000a
- **Remaining question:** none for this defect; the sheet now refuses with the input named in the error message

## INV34-001752 — `core/engineering/well_control_kill_sheet.py:292`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** `frac_gradient_psi_ft` is one of the gated raw inputs (``required_raw``, 259-272) and the builder lists the inputs the composite computation actually consumes (257) and ``compute_kill_sheet`` refuses whenever one is absent: 'A kill sheet computed from absent kick data looks plausible and is wrong (e.g. absent SIDPP becomes "no overpressure"). Refuse instead.' (436-443), returning ``KillSheetResult(success=False, error=KILL_INPUT_INVALID...)``. An absent value therefore cannot reach the arithmetic as 0.0: it refuses. The widgets hand the builder None for their not-supplied sentinel ("Read a kill-sheet input; the sentinel reads back as ``None``", tabs/w13_Engineering_Calculator.py:5227-5231), so the None case is real.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-001753 — `core/engineering/well_control_kill_sheet.py:289`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** `hole_size_in` is one of the gated raw inputs (``required_raw``, 259-272) and the builder lists the inputs the composite computation actually consumes (257) and ``compute_kill_sheet`` refuses whenever one is absent: 'A kill sheet computed from absent kick data looks plausible and is wrong (e.g. absent SIDPP becomes "no overpressure"). Refuse instead.' (436-443), returning ``KillSheetResult(success=False, error=KILL_INPUT_INVALID...)``. An absent value therefore cannot reach the arithmetic as 0.0: it refuses. The widgets hand the builder None for their not-supplied sentinel ("Read a kill-sheet input; the sentinel reads back as ``None``", tabs/w13_Engineering_Calculator.py:5227-5231), so the None case is real.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-001755 — `core/engineering/well_control_kill_sheet.py:291`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** `mw_pcf` is one of the gated raw inputs (``required_raw``, 259-272) and the builder lists the inputs the composite computation actually consumes (257) and ``compute_kill_sheet`` refuses whenever one is absent: 'A kill sheet computed from absent kick data looks plausible and is wrong (e.g. absent SIDPP becomes "no overpressure"). Refuse instead.' (436-443), returning ``KillSheetResult(success=False, error=KILL_INPUT_INVALID...)``. An absent value therefore cannot reach the arithmetic as 0.0: it refuses. The widgets hand the builder None for their not-supplied sentinel ("Read a kill-sheet input; the sentinel reads back as ``None``", tabs/w13_Engineering_Calculator.py:5227-5231), so the None case is real.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-001759 — `core/engineering/well_control_kill_sheet.py:295`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** `pit_gain_bbl` is one of the gated raw inputs (``required_raw``, 259-272) and the builder lists the inputs the composite computation actually consumes (257) and ``compute_kill_sheet`` refuses whenever one is absent: 'A kill sheet computed from absent kick data looks plausible and is wrong (e.g. absent SIDPP becomes "no overpressure"). Refuse instead.' (436-443), returning ``KillSheetResult(success=False, error=KILL_INPUT_INVALID...)``. An absent value therefore cannot reach the arithmetic as 0.0: it refuses. The widgets hand the builder None for their not-supplied sentinel ("Read a kill-sheet input; the sentinel reads back as ``None``", tabs/w13_Engineering_Calculator.py:5227-5231), so the None case is real.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-001760 — `core/engineering/well_control_kill_sheet.py:300`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** `pump_output_bbl_stk` is one of the gated raw inputs (``required_raw``, 259-272) and the builder lists the inputs the composite computation actually consumes (257) and ``compute_kill_sheet`` refuses whenever one is absent: 'A kill sheet computed from absent kick data looks plausible and is wrong (e.g. absent SIDPP becomes "no overpressure"). Refuse instead.' (436-443), returning ``KillSheetResult(success=False, error=KILL_INPUT_INVALID...)``. An absent value therefore cannot reach the arithmetic as 0.0: it refuses. The widgets hand the builder None for their not-supplied sentinel ("Read a kill-sheet input; the sentinel reads back as ``None``", tabs/w13_Engineering_Calculator.py:5227-5231), so the None case is real.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-001761 — `core/engineering/well_control_kill_sheet.py:296`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** `scr1_psi` is one of the gated raw inputs (``required_raw``, 259-272) and the builder lists the inputs the composite computation actually consumes (257) and ``compute_kill_sheet`` refuses whenever one is absent: 'A kill sheet computed from absent kick data looks plausible and is wrong (e.g. absent SIDPP becomes "no overpressure"). Refuse instead.' (436-443), returning ``KillSheetResult(success=False, error=KILL_INPUT_INVALID...)``. An absent value therefore cannot reach the arithmetic as 0.0: it refuses. The widgets hand the builder None for their not-supplied sentinel ("Read a kill-sheet input; the sentinel reads back as ``None``", tabs/w13_Engineering_Calculator.py:5227-5231), so the None case is real.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-001762 — `core/engineering/well_control_kill_sheet.py:297`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** `scr1_spm` is echoed, not consumed: ``scr1_spm``/``scr2_spm`` are documented echo-only display metadata (257-258), and a grep of the module shows ``scr2_psi`` is never read by ``compute_kill_sheet`` either (only ``scr1_psi`` at 456); an absent value in these display fields reaches nothing computed. the builder lists the inputs the composite computation actually consumes (257) and ``compute_kill_sheet`` refuses whenever one is absent: 'A kill sheet computed from absent kick data looks plausible and is wrong (e.g. absent SIDPP becomes "no overpressure"). Refuse instead.' (436-443), returning ``KillSheetResult(success=False, error=KILL_INPUT_INVALID...)``. The defect it could otherwise carry is impossible here (nothing computed reads it), and the module says so in the same comment that lists the gate.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-001763 — `core/engineering/well_control_kill_sheet.py:298`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** `scr2_psi` is not consumed by the composite computation (verified: the module reads ``scr1_psi`` at 456 and never ``scr2_psi`` - it exists for the second-circulation echo), so an absent value cannot affect a computed result. ``scr1_spm``/``scr2_spm`` are documented echo-only display metadata (257-258), and a grep of the module shows ``scr2_psi`` is never read by ``compute_kill_sheet`` either (only ``scr1_psi`` at 456); an absent value in these display fields reaches nothing computed.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-001764 — `core/engineering/well_control_kill_sheet.py:299`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** `scr2_spm` is echoed, not consumed: ``scr1_spm``/``scr2_spm`` are documented echo-only display metadata (257-258), and a grep of the module shows ``scr2_psi`` is never read by ``compute_kill_sheet`` either (only ``scr1_psi`` at 456); an absent value in these display fields reaches nothing computed.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-001765 — `core/engineering/well_control_kill_sheet.py:288`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** `tvd_m` is one of the gated raw inputs (``required_raw``, 259-272) and the builder lists the inputs the composite computation actually consumes (257) and ``compute_kill_sheet`` refuses whenever one is absent: 'A kill sheet computed from absent kick data looks plausible and is wrong (e.g. absent SIDPP becomes "no overpressure"). Refuse instead.' (436-443), returning ``KillSheetResult(success=False, error=KILL_INPUT_INVALID...)``. An absent value therefore cannot reach the arithmetic as 0.0: it refuses. The widgets hand the builder None for their not-supplied sentinel ("Read a kill-sheet input; the sentinel reads back as ``None``", tabs/w13_Engineering_Calculator.py:5227-5231), so the None case is real.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-001766 — `core/engineering/well_control_kill_sheet.py:294`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** `sicp_psi` is one of the gated raw inputs (``required_raw``, 259-272) and the builder lists the inputs the composite computation actually consumes (257) and ``compute_kill_sheet`` refuses whenever one is absent: 'A kill sheet computed from absent kick data looks plausible and is wrong (e.g. absent SIDPP becomes "no overpressure"). Refuse instead.' (436-443), returning ``KillSheetResult(success=False, error=KILL_INPUT_INVALID...)``. An absent value therefore cannot reach the arithmetic as 0.0: it refuses. The widgets hand the builder None for their not-supplied sentinel ("Read a kill-sheet input; the sentinel reads back as ``None``", tabs/w13_Engineering_Calculator.py:5227-5231), so the None case is real.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-001767 — `core/engineering/well_control_kill_sheet.py:293`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** `sidpp_psi` is one of the gated raw inputs (``required_raw``, 259-272) and the builder lists the inputs the composite computation actually consumes (257) and ``compute_kill_sheet`` refuses whenever one is absent: 'A kill sheet computed from absent kick data looks plausible and is wrong (e.g. absent SIDPP becomes "no overpressure"). Refuse instead.' (436-443), returning ``KillSheetResult(success=False, error=KILL_INPUT_INVALID...)``. An absent value therefore cannot reach the arithmetic as 0.0: it refuses. The widgets hand the builder None for their not-supplied sentinel ("Read a kill-sheet input; the sentinel reads back as ``None``", tabs/w13_Engineering_Calculator.py:5227-5231), so the None case is real.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-001957 — `core/hydraulics_engine.py:395`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class C)
- **Symbol:** `AdvancedHydraulicsEngine.calculate`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** The swallowed ValueError is ``calc_critical_flow_rate``'s declared input guard - 'Hole size and pipe OD must be > 0', 'Hole size must be > pipe OD', 'MW and PV must be > 0', 'Yield point cannot be negative' (raised at the top of the function) - and the fields it protects default to 0.0/"" ('not computed'), which the single consumer treats as *no data* rather than as a measured zero: tabs/w13_Engineering_Calculator.py:1588 renders the critical-flow block only ``if getattr(r, "critical_flow_rate_gpm", 0) > 0``. Value and section name are assigned together inside the same ``try`` (392-394), so a skipped section can never be reported under another section's name; a computed Qc is strictly positive (velocity x area), so 0.0 is never a legitimate measurement.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-002049 — `core/inventory_semantics.py:64`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class D)
- **Symbol:** `derive_closing`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** `derive_closing`'s docstring defines the result contract - 'Closing stock = opening + received - used, or None when opening unknown. Never returns a fabricated 0.0 when the opening is unknown.' - and the module documents movement semantics separately: ``normalize_movement`` 'Absent movement means zero; malformed/nonfinite/bool input is an error.' (67-70). The ``or 0.0`` therefore implements two documented rules: an unknown opening propagates as None (62-63) and an absent movement is a real zero. ``received`` is the movement operand adjudicated here.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-002050 — `core/inventory_semantics.py:64`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class D)
- **Symbol:** `derive_closing`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** Second register record for the statement adjudicated under INV34-002049 (core/inventory_semantics.py:64 - the same statement, rule R-DEF-RETURN-NUM twice (``received`` and ``used`` operands of one expression)); the register's two rules fired on one construct, so this id adds no independent behaviour. Adjudicated once under INV34-002049: `derive_closing`'s docstring defines the result contract - 'Closing stock = opening + received - used, or None when opening unknown. Never returns a fabricated 0.0 when the opening is unknown.' - and the module documents movement semantics separately: ``normalize_movement`` 'Absent movement means zero; malformed/nonfinite/bool input is an error.' (67-70). The ``or 0.0`` therefore implements two documented rules: an unknown opening propagates as None (62-63) and an absent movement is a real zero.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-002873 — `core/time_utils.py:68`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class C)
- **Symbol:** `TimeLineEdit._on_editing_finished`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** `_on_editing_finished` cannot commit invalid text: after both parse attempts the method restores the last accepted value explicitly - 'if invalid, return the previous value' (84-88), re-rendering ``24:00`` or the stored ``_hour``/``_minute``. The swallowed ValueError is the *expected* outcome of testing whether the typed text parses at all. The swallow is compensated in the same method, so the failure it hides cannot reach the widget's value.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-002874 — `core/time_utils.py:81`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class C)
- **Symbol:** `TimeLineEdit._on_editing_finished`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** `_on_editing_finished` cannot commit invalid text: after both parse attempts the method restores the last accepted value explicitly - 'if invalid, return the previous value' (84-88), re-rendering ``24:00`` or the stored ``_hour``/``_minute``. The swallowed ValueError is the *expected* outcome of testing whether the typed text parses at all. (This is the compact HHMM branch of the same method; the same restore-at-the-end applies to both branches.)
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-002875 — `core/time_utils.py:168`

- **Rule / kind:** `R-EXC-PASS` / `typed-exception` (HIGH, class C)
- **Symbol:** `TimeValidator.validate`
- **Register question:** May this exception be swallowed with `pass`?
- **Evidence:** `TimeValidator.validate` never *accepts* through the swallow: Acceptable is returned only after the range check succeeds (166-167); anything that fails falls through to the explicit prefix checks and ends in ``QValidator.Invalid`` (176-186, 'Arbitrary text such as ``abc`` must be invalid rather than silently accepted'), with out-of-range times ('25:99') at best Intermediate - and Intermediate/Invalid text cannot be committed because the editing-finished handler restores the previous value (84-88).
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-004595 — `tabs/w13_Engineering_Calculator.py:125`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `broad-exception` (HIGH, class D)
- **Symbol:** `DrillingCalculationEngine.calc_buoyancy_factor`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** The wrapped call is the canonical engine delegate, whose only documented failures are physically invalid input (``require_number`` for non-finite, and 'mud_density_ppg must be > 0' / steel-density checks in TorqueDragEngine.buoyancy_factor) and whose fallback here is the same pinned legacy zero as the no-input path (tests/test_single_source_guard.py:107-108). The caller feeds it a spin box bounded at 0..200 pcf (``self._make_dspin(90, 0, 200, 1, " pcf")``, 3554), while the engine only raises at a mud density at or above the steel density (490 pcf) - so the branch is unreachable through the delivered UI and cannot fabricate a card. Residual (recorded, not a defect claim): if the mud-weight bound were ever raised near steel density, the 0.0 fallback would render as a zero hook load instead of the engine's reason.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-004597 — `tabs/w13_Engineering_Calculator.py:125`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `broad-exception` (HIGH, class D)
- **Symbol:** `DrillingCalculationEngine.calc_buoyancy_factor`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** Second register record for the statement adjudicated under INV34-004595 (tabs/w13_Engineering_Calculator.py:125 - the same handler (second rule on the same `except Exception` line)); the register's two rules fired on one construct, so this id adds no independent behaviour. Adjudicated once under INV34-004595: unreachable through the delivered spin-box range; 0.0 is the pinned legacy answer
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-004606 — `tabs/w13_Engineering_Calculator.py:125`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `broad-exception` (HIGH, class D)
- **Symbol:** `DrillingCalculationEngine.calc_buoyancy_factor`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** Second register record for the statement adjudicated under INV34-004595 (tabs/w13_Engineering_Calculator.py:125 - the same handler (third rule on the same line)); the register's two rules fired on one construct, so this id adds no independent behaviour. Adjudicated once under INV34-004595: as above
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007522 — `core/engineering/well_control_kill_sheet.py:288`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** Second register record for the statement adjudicated under INV34-001765 (core/engineering/well_control_kill_sheet.py:288 - the same `tvd_m` statement, rule pair R-DEF-RETURN-NUM/or-zero twice on one line); the register's two rules fired on one construct, so this id adds no independent behaviour. Adjudicated once under INV34-001765: `tvd_m`: `tvd_m` is one of the gated raw inputs (``required_raw``, 259-272) and the builder lists the inputs the composite computation actually consumes (257) ...
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007523 — `core/engineering/well_control_kill_sheet.py:289`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** Second register record for the statement adjudicated under INV34-001753 (core/engineering/well_control_kill_sheet.py:289 - the same `hole_size_in` statement, rule pair R-DEF-RETURN-NUM/or-zero twice on one line); the register's two rules fired on one construct, so this id adds no independent behaviour. Adjudicated once under INV34-001753: `hole_size_in`: `hole_size_in` is one of the gated raw inputs (``required_raw``, 259-272) and the builder lists the inputs the composite computation actually consumes...
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007524 — `core/engineering/well_control_kill_sheet.py:290`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** Second register record for the statement adjudicated under INV34-001751 (core/engineering/well_control_kill_sheet.py:290 - the same casing-ID statement, rule pair R-DEF-RETURN-NUM/or-zero twice on one line); the register's two rules fired on one construct, so this id adds no independent behaviour. Adjudicated once under INV34-001751: one statement, one defect, one fix (commit ff2000a); the defect is recorded under INV34-001751
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007525 — `core/engineering/well_control_kill_sheet.py:291`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** Second register record for the statement adjudicated under INV34-001755 (core/engineering/well_control_kill_sheet.py:291 - the same `mw_pcf` statement, rule pair R-DEF-RETURN-NUM/or-zero twice on one line); the register's two rules fired on one construct, so this id adds no independent behaviour. Adjudicated once under INV34-001755: `mw_pcf`: `mw_pcf` is one of the gated raw inputs (``required_raw``, 259-272) and the builder lists the inputs the composite computation actually consumes (257)...
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007526 — `core/engineering/well_control_kill_sheet.py:292`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** Second register record for the statement adjudicated under INV34-001752 (core/engineering/well_control_kill_sheet.py:292 - the same `frac_gradient_psi_ft` statement, rule pair R-DEF-RETURN-NUM/or-zero twice on one line); the register's two rules fired on one construct, so this id adds no independent behaviour. Adjudicated once under INV34-001752: `frac_gradient_psi_ft`: `frac_gradient_psi_ft` is one of the gated raw inputs (``required_raw``, 259-272) and the builder lists the inputs the composite computation actually ...
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007527 — `core/engineering/well_control_kill_sheet.py:293`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** Second register record for the statement adjudicated under INV34-001767 (core/engineering/well_control_kill_sheet.py:293 - the same `sidpp_psi` statement, rule pair R-DEF-RETURN-NUM/or-zero twice on one line); the register's two rules fired on one construct, so this id adds no independent behaviour. Adjudicated once under INV34-001767: `sidpp_psi`: `sidpp_psi` is one of the gated raw inputs (``required_raw``, 259-272) and the builder lists the inputs the composite computation actually consumes (2...
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007528 — `core/engineering/well_control_kill_sheet.py:294`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** Second register record for the statement adjudicated under INV34-001766 (core/engineering/well_control_kill_sheet.py:294 - the same `sicp_psi` statement, rule pair R-DEF-RETURN-NUM/or-zero twice on one line); the register's two rules fired on one construct, so this id adds no independent behaviour. Adjudicated once under INV34-001766: `sicp_psi`: `sicp_psi` is one of the gated raw inputs (``required_raw``, 259-272) and the builder lists the inputs the composite computation actually consumes (25...
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007529 — `core/engineering/well_control_kill_sheet.py:295`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** Second register record for the statement adjudicated under INV34-001759 (core/engineering/well_control_kill_sheet.py:295 - the same `pit_gain_bbl` statement, rule pair R-DEF-RETURN-NUM/or-zero twice on one line); the register's two rules fired on one construct, so this id adds no independent behaviour. Adjudicated once under INV34-001759: `pit_gain_bbl`: `pit_gain_bbl` is one of the gated raw inputs (``required_raw``, 259-272) and the builder lists the inputs the composite computation actually consumes...
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007530 — `core/engineering/well_control_kill_sheet.py:296`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** Second register record for the statement adjudicated under INV34-001761 (core/engineering/well_control_kill_sheet.py:296 - the same `scr1_psi` statement, rule pair R-DEF-RETURN-NUM/or-zero twice on one line); the register's two rules fired on one construct, so this id adds no independent behaviour. Adjudicated once under INV34-001761: `scr1_psi`: `scr1_psi` is one of the gated raw inputs (``required_raw``, 259-272) and the builder lists the inputs the composite computation actually consumes (25...
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007531 — `core/engineering/well_control_kill_sheet.py:297`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** Second register record for the statement adjudicated under INV34-001762 (core/engineering/well_control_kill_sheet.py:297 - the same `scr1_spm` statement, rule pair R-DEF-RETURN-NUM/or-zero twice on one line); the register's two rules fired on one construct, so this id adds no independent behaviour. Adjudicated once under INV34-001762: `scr1_spm`: `scr1_spm` is echoed, not consumed: ``scr1_spm``/``scr2_spm`` are documented echo-only display metadata (257-258), and a grep of the module shows ``sc...
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007532 — `core/engineering/well_control_kill_sheet.py:298`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** Second register record for the statement adjudicated under INV34-001763 (core/engineering/well_control_kill_sheet.py:298 - the same `scr2_psi` statement, rule pair R-DEF-RETURN-NUM/or-zero twice on one line); the register's two rules fired on one construct, so this id adds no independent behaviour. Adjudicated once under INV34-001763: `scr2_psi`: `scr2_psi` is not consumed by the composite computation (verified: the module reads ``scr1_psi`` at 456 and never ``scr2_psi`` - it exists for the sec...
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007533 — `core/engineering/well_control_kill_sheet.py:299`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** Second register record for the statement adjudicated under INV34-001764 (core/engineering/well_control_kill_sheet.py:299 - the same `scr2_spm` statement, rule pair R-DEF-RETURN-NUM/or-zero twice on one line); the register's two rules fired on one construct, so this id adds no independent behaviour. Adjudicated once under INV34-001764: `scr2_spm`: `scr2_spm` is echoed, not consumed: ``scr1_spm``/``scr2_spm`` are documented echo-only display metadata (257-258), and a grep of the module shows ``sc...
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007534 — `core/engineering/well_control_kill_sheet.py:300`

- **Rule / kind:** `R-DEF-RETURN-NUM` / `or-zero` (HIGH, class C)
- **Symbol:** `build_canonical_kill_sheet_inputs`
- **Register question:** Is this numeric default returned to the caller the real value?
- **Evidence:** Second register record for the statement adjudicated under INV34-001760 (core/engineering/well_control_kill_sheet.py:300 - the same `pump_output_bbl_stk` statement, rule pair R-DEF-RETURN-NUM/or-zero twice on one line); the register's two rules fired on one construct, so this id adds no independent behaviour. Adjudicated once under INV34-001760: `pump_output_bbl_stk`: `pump_output_bbl_stk` is one of the gated raw inputs (``required_raw``, 259-272) and the builder lists the inputs the composite computation actually c...
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007572 — `core/hydraulics_engine.py:396`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class C)
- **Symbol:** `AdvancedHydraulicsEngine.calculate`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for the statement adjudicated under INV34-001957 (core/hydraulics_engine.py:395/396 - the same handler (rule pair R-EXC-PASS + R-PASS-EXC)); the register's two rules fired on one construct, so this id adds no independent behaviour. Adjudicated once under INV34-001957: the guard is the engine's declared invalid-input check and 0.0 means 'not computed' to its only consumer
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007842 — `core/time_utils.py:69`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class C)
- **Symbol:** `TimeLineEdit._on_editing_finished`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for the statement adjudicated under INV34-002873 (core/time_utils.py:68/69 - the same handler (rule pair R-EXC-PASS + R-PASS-EXC on one `except ValueError` line)); the register's two rules fired on one construct, so this id adds no independent behaviour. Adjudicated once under INV34-002873: invalid input restores the previous value (84-88)
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007843 — `core/time_utils.py:82`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class C)
- **Symbol:** `TimeLineEdit._on_editing_finished`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for the statement adjudicated under INV34-002874 (core/time_utils.py:81/82 - the same handler (rule pair)); the register's two rules fired on one construct, so this id adds no independent behaviour. Adjudicated once under INV34-002874: invalid input restores the previous value (84-88)
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-007845 — `core/time_utils.py:169`

- **Rule / kind:** `R-PASS-EXC` / `pass-statement` (HIGH, class C)
- **Symbol:** `TimeValidator.validate`
- **Register question:** May this handler body be `pass` only?
- **Evidence:** Second register record for the statement adjudicated under INV34-002875 (core/time_utils.py:168/169 - the same handler (rule pair)); the register's two rules fired on one construct, so this id adds no independent behaviour. Adjudicated once under INV34-002875: the validator still ends in Invalid/Intermediate, never Acceptable
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-008222 — `tabs/w13_Engineering_Calculator.py:4934`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `broad-exception` (HIGH, class D)
- **Symbol:** `EngineeringCalculatorTab._ac_recalculate`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** The engine's refusal is the documented contract (TrajectoryEngine requires monotonic MD and detects duplicate/non-monotonic input), and the handler's response is to recompute nothing: the raw MD/inc/azi the user typed stay in the model, the derived columns are only written on success (4936-4940 / 5100-5105), and these survey lists are not persisted anywhere (no save path references ``ac_offset_surveys``/``dd_surveys`` - verified by grep), so the outcome is a preview with unfilled derived columns rather than a stored wrong number. Residual (recorded, not a defect claim): the reason is not surfaced to the user and a previous successful computation's columns can remain visible next to edited raw values until a successful recompute; the engine's error is dropped. Neither is a fabricated value, and no module contract requires a message here. Site: ``_ac_recalculate`` (anti-collision offset well).
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-008226 — `tabs/w13_Engineering_Calculator.py:5098`

- **Rule / kind:** `R-EXC-SILENT-RETURN` / `broad-exception` (HIGH, class D)
- **Symbol:** `EngineeringCalculatorTab._dd_recalculate_from`
- **Register question:** Is returning this fallback value without logging correct?
- **Evidence:** The engine's refusal is the documented contract (TrajectoryEngine requires monotonic MD and detects duplicate/non-monotonic input), and the handler's response is to recompute nothing: the raw MD/inc/azi the user typed stay in the model, the derived columns are only written on success (4936-4940 / 5100-5105), and these survey lists are not persisted anywhere (no save path references ``ac_offset_surveys``/``dd_surveys`` - verified by grep), so the outcome is a preview with unfilled derived columns rather than a stored wrong number. Residual (recorded, not a defect claim): the reason is not surfaced to the user and a previous successful computation's columns can remain visible next to edited raw values until a successful recompute; the engine's error is dropped. Neither is a fabricated value, and no module contract requires a message here. Site: ``_dd_recalculate_from`` (directional-drilling survey table).
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-008826 — `tabs/w13_Engineering_Calculator.py:119`

- **Rule / kind:** `R-TRUTH-NUMERIC` / `truthiness-bare` (HIGH, class D)
- **Symbol:** `DrillingCalculationEngine.calc_buoyancy_factor`
- **Register question:** May this numeric subject be tested for truthiness?
- **Evidence:** Zero is not a legitimate value for this parameter (a 0 pcf mud is physically meaningless), and the zero-input answer is a pinned legacy contract rather than an invention: tests/test_single_source_guard.py:107-108 states 'no input -> legacy 0 (no crash, no invented value)' and asserts ``calc_buoyancy_factor(0.0) == 0.0``. The canonical engine refuses the same input explicitly ('mud_density_ppg must be > 0', core/engineering/engines/torque_drag.py), so the wrapper's ``not x or x <= 0`` guard is equivalent to the engine's own rule for every float, including None.
- **Classification:** INTENTIONAL
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-008852 — `tabs/w3_drilling_report.py:907`

- **Rule / kind:** `R-PARAM-ARITH` / `numeric-parameter-default` (HIGH, class C)
- **Symbol:** `DrillingParametersTab.load_from_dict.safe_val`
- **Register question:** Is arithmetic on this parameter domain-correct?
- **Evidence:** The parameter's domain is the widget's own entry range: ``safe_val`` loads operator-entry spin boxes whose floor is a legal zero (e.g. ``self.wob_min.setRange(0, 100)``, 475) and whose 'empty' state is that same 0 (``clear_form`` sets 0), and zero is a legal WOB/RPM/torque value - so the default cannot fabricate a measurement. The same function shows the deliberate split: ``safe_opt`` carries the documented contract 'Stored value, or None when the report holds no recorded number.' (916-917) and is what the *recorded/computed* field uses (``_set_calc(self.tfa_value, safe_opt("tfa"))``, 962). Residual (recorded, not a defect claim): re-saving a report whose stored value was NULL normalises that entry field to 0 (a legal domain value); if the product ever needs 'not recorded' for entry fields, that is a sentinel-widget feature, not a defect in this loader.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-008876 — `tabs/w3_drilling_report.py:1628`

- **Rule / kind:** `R-PARAM-ARITH` / `numeric-parameter-default` (HIGH, class C)
- **Symbol:** `MudReportTab.load_from_dict.safe_val`
- **Register question:** Is arithmetic on this parameter domain-correct?
- **Evidence:** Second register record for the statement adjudicated under INV34-008852 (tabs/w3_drilling_report.py:1628 - the identical ``safe_val`` helper in MudReportTab's load_from_dict); the register's two rules fired on one construct, so this id adds no independent behaviour. Adjudicated once under INV34-008852: The parameter's domain is the widget's own entry range: ``safe_val`` loads operator-entry spin boxes whose floor is a legal zero (e.g. ``self.wob_min.setRange(0, 100)``, 475) and whose 'empty' state is that same 0 (``clear_form`` sets 0), and zero is a legal WOB/RPM/torque value - so the default cannot fabricate a measurement. The same function shows the deliberate split: ``safe_opt`` carries the documented contract 'Stored value, or None when the report holds no recorded number.' (916-917) and is what the *recorded/computed* field uses (``_set_calc(self.tfa_value, safe_opt("tfa"))``, 962). Residual (recorded, not a defect claim): re-saving a report whose stored value was NULL normalises that entry field to 0 (a legal domain value); if the product ever needs 'not recorded' for entry fields, that is a sentinel-widget feature, not a defect in this loader.
- **Classification:** DUPLICATE/FALSE-POSITIVE
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

## INV34-011052 — `tests/test_real_oeoc_golden.py:381`

- **Rule / kind:** `R-RED-ZERO` / `sum-or-zero` (HIGH, class C)
- **Symbol:** `Test24HTimeLog.test_db_stores_2400_row`
- **Register question:** Is this zero reduction correct?
- **Evidence:** A test-local reduction, and the assertion pins the sum it feeds: ``total = sum(r.duration or 0 for r in rows)`` is immediately checked against ``pytest.approx(24.0)`` (382) after asserting there are exactly 7 rows with the last one ending at 00:00 and a 0.5 h duration (376-380). A NULL duration would therefore make the total short of 24.0 and fail the test (it cannot mask a missing measurement), and the test's subject is the 24:00 row's storage, not the ``or 0`` idiom.
- **Classification:** VERIFIED-CORRECT
- **Defect:** no
- **Test:** not applicable (no behaviour change)
- **Commit:** audit-only (no code change; batch code commit ff2000a, evidence commit recorded in the ledger)
- **Remaining question:** none

